from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.ml.query_router import predict_intent
from backend.services.keyword_extractor import extract_slots, Slots

from backend.services.hotel_insights_localdb import get_hotel_insights_localdb
from backend.services.hotel_insights_rapidapi import get_hotel_insights

from backend.services.location_geoid_converter import convert_geo_id, CITY_GEOIDS
from backend.models import generate_text


logger = logging.getLogger(__name__)


# Intention labels
EXPLORE_LOCAL = "EXPLORE_LOCAL"
LIVE_PRICES = "LIVE_PRICES"
NEEDS_DATES = "NEEDS_DATES"

LOCAL_SLA_MS = 1000
RAPIDAPI_SLA_MIN_MS = 2000
RAPIDAPI_SLA_MAX_MS = 6000
RAPIDAPI_LLM_BUDGET_MS = 1200
LOCAL_LLM_BUDGET_MS = 900


HOTEL_WORDS = (
    "hotel", "resort", "villa", "guesthouse", "accommodation",
    "stay", "lodge", "hostel", "apartment"
)

BOOKING_WORDS = (
    "price", "prices", "cost", "rate", "rates", "how much",
    "availability", "available", "vacancy", "rooms available",
    "book", "booking", "reserve",
    "check-in", "check out", "check-out",
    "tonight", "tomorrow", "weekend", "next week", "next month",
    "for 1 night", "for 2 nights", "for 3 nights"
)

_DATE_SIGNAL_RE = re.compile(
    r"(\b\d{4}-\d{2}-\d{2}\b|\bcheck[\s-]?in\b|\bcheck[\s-]?out\b|\btonight\b|\btomorrow\b|\bnext week\b|\bnext month\b)",
    re.IGNORECASE,
) 
_NATURAL_DATE_RANGE_RE = re.compile(
    r"\b(?:from\s+)?([a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?|\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s+\d{4})?)\s+(?:to|until|till|\-)\s+([a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?|\d{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s+\d{4})?)\b",
    re.IGNORECASE,
)

_PRICE_MIN_RE = re.compile(r"minimum\s+price\s+(\d+)", re.IGNORECASE)
_PRICE_MAX_RE = re.compile(r"maximum\s+price\s+(\d+)", re.IGNORECASE)
_FAST_BETWEEN_PRICE_RE = re.compile(r"\bbetween\s+([\d.,]+k?)\s+(?:and|to)\s+([\d.,]+k?)\b", re.IGNORECASE)
_FAST_UNDER_PRICE_RE = re.compile(r"\b(?:under|below|less than|up to)\s+([\d.,]+k?)\b", re.IGNORECASE)
_FAST_OVER_PRICE_RE = re.compile(r"\b(?:over|above|more than|at least)\s+([\d.,]+k?)\b(?!\s*star)", re.IGNORECASE)
_RATING_RE = re.compile(r"rating\s+(\d)(?:\+)?", re.IGNORECASE)
_STAR_RATING_RE = re.compile(r"\b(?:over|above|at least|minimum|min)?\s*(\d)\s*\+?\s*star(?:s)?\b", re.IGNORECASE)
_FAST_MONEY_TOKEN_RE = re.compile(r"\b\d+(?:\.\d+)?\s*k\b|\b\d{4,}\b", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_ADULTS_RE = re.compile(r"(\d+)\s*(adults|adult|people|persons|guests)", re.IGNORECASE)
_ROOMS_RE = re.compile(r"(\d+)\s*(rooms|room)", re.IGNORECASE)
_FILTER_HINT_RE = re.compile(
    r"\b(under|below|less than|up to|above|over|more than|at least|between|budget|cheap|cheaper|affordable|rating|star)\b",
    re.IGNORECASE,
)

# helper function to check if any of the keywords are in the text
def _contains_any(text: str, keywords: Tuple[str, ...]) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords) # if any of the keywords are found in the text, return True


def _apply_overrides(pred_intent: str, query: str, slots) -> str:
    """
    Rule layer to stabilize TF-IDF mistakes.
    Priority:
      1) If dates exist -> LIVE_PRICES
      2) If booking-like query but missing dates -> NEEDS_DATES
      3) If hotel-like query -> EXPLORE_LOCAL (unless already live/needs_dates)
    """
    has_hotel_signal = _contains_any(query, HOTEL_WORDS)
    has_booking_signal = _contains_any(query, BOOKING_WORDS)

    # If explicit dates exist -> must be LIVE_PRICES
    if getattr(slots, "check_in", None) and getattr(slots, "check_out", None):
        return LIVE_PRICES

    # Booking/price intent but missing dates -> ask for dates
    if has_booking_signal and not (getattr(slots, "check_in", None) and getattr(slots, "check_out", None)):
        return NEEDS_DATES

    # Hotel-like queries should go local explore by default
    if has_hotel_signal and pred_intent not in (LIVE_PRICES, NEEDS_DATES):
        return EXPLORE_LOCAL

    return pred_intent


def _coerce_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _fast_money_to_int(value: str) -> Optional[int]:
    if not value:
        return None

    cleaned = value.strip().lower().replace(",", "")
    cleaned = re.sub(r"(lkr|rs\.?|rupees?|rup)\b", "", cleaned).strip()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(k)?", cleaned, re.IGNORECASE)
    if not match:
        return None

    amount = float(match.group(1))
    if match.group(2):
        amount *= 1000
    return int(amount)


def _parse_natural_date_token(token: str, today: date) -> Optional[date]:
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", (token or "").strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    formats = (
        "%d %B %Y",
        "%d %b %Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B",
        "%d %b",
        "%B %d",
        "%b %d",
    )

    for fmt in formats:
        try:
            candidate = datetime.strptime(cleaned, fmt).date()
            if "%Y" not in fmt:
                candidate = candidate.replace(year=today.year)
                if candidate < today - timedelta(days=30):
                    candidate = candidate.replace(year=today.year + 1)
            return candidate
        except ValueError:
            continue

    return None


def _infer_dates_from_text(text: str) -> tuple[Optional[date], Optional[date]]:
    iso_dates = _ISO_DATE_RE.findall(text)
    if len(iso_dates) >= 2:
        try:
            return date.fromisoformat(iso_dates[0]), date.fromisoformat(iso_dates[1])
        except ValueError:
            pass

    today = date.today()
    natural_range_match = _NATURAL_DATE_RANGE_RE.search(text or "")
    if natural_range_match:
        first = _parse_natural_date_token(natural_range_match.group(1), today)
        second = _parse_natural_date_token(natural_range_match.group(2), today)
        if first and second:
            if second < first:
                second = second.replace(year=second.year + 1)
            return first, second

    lowered = (text or "").lower()

    if "tonight" in lowered:
        return today, today + timedelta(days=1)

    if "tomorrow" in lowered:
        start = today + timedelta(days=1)
        return start, start + timedelta(days=1)

    if "weekend" in lowered:
        days_until_saturday = (5 - today.weekday()) % 7
        start = today + timedelta(days=days_until_saturday)
        return start, start + timedelta(days=2)

    if "next week" in lowered:
        start = today + timedelta(days=7)
        return start, start + timedelta(days=2)

    if "next month" in lowered:
        start = today + timedelta(days=30)
        return start, start + timedelta(days=2)

    return None, None


def _fast_default_budget_cap(text: str) -> Optional[int]:
    token_match = _FAST_MONEY_TOKEN_RE.search(text or "")
    if not token_match:
        return None
    return _fast_money_to_int(token_match.group(0))


def _apply_context_slots(slots: Slots, context_slots: Dict[str, Any]) -> None:
    if not isinstance(context_slots, dict):
        return

    if not getattr(slots, "location", None) and context_slots.get("location"):
        slots.location = str(context_slots.get("location"))

    if not getattr(slots, "check_in", None):
        slots.check_in = _coerce_date(context_slots.get("check_in"))
    if not getattr(slots, "check_out", None):
        slots.check_out = _coerce_date(context_slots.get("check_out"))

    if not getattr(slots, "adults", None):
        slots.adults = _coerce_int(context_slots.get("adults"))
    if not getattr(slots, "rooms", None):
        slots.rooms = _coerce_int(context_slots.get("rooms"))
    if not getattr(slots, "price_min", None):
        slots.price_min = _coerce_int(context_slots.get("price_min"))
    if not getattr(slots, "price_max", None):
        slots.price_max = _coerce_int(context_slots.get("price_max"))

    current_rating = getattr(slots, "rating", None)
    if current_rating is None:
        setattr(slots, "rating", _coerce_int(context_slots.get("rating")))


def _has_local_filter_signal(query: str, slots: Slots) -> bool:
    if _FILTER_HINT_RE.search(query or ""):
        return True

    return any(
        value is not None
        for value in (
            getattr(slots, "price_min", None),
            getattr(slots, "price_max", None),
            getattr(slots, "rating", None),
            getattr(slots, "adults", None),
            getattr(slots, "rooms", None),
        )
    )


def _is_short_followup(query: str) -> bool:
    words = [w for w in re.split(r"\s+", (query or "").strip()) if w]
    if len(words) <= 6:
        return True
    q = (query or "").lower()
    return any(marker in q for marker in ("what about", "how about", "cheaper", "similar", "those", "that one", "these"))


def _try_fast_intent_and_slots(query: str, fallback_location: Optional[str] = None) -> Tuple[str, float, Slots] | None:
    text = (query or "").strip()
    lowered = text.lower()
    if not text:
        return None

    matched_location = None
    for city in CITY_GEOIDS.keys():
        city_l = city.lower()
        if re.search(rf"\b{re.escape(city_l)}\b", lowered):
            matched_location = city
            break

    if not matched_location:
        in_match = re.search(r"\bin\s+([a-zA-Z\s]+)", text)
        if in_match:
            raw = in_match.group(1).strip(" ,.")
            if raw:
                matched_location = raw.title()

    if not matched_location and fallback_location:
        matched_location = fallback_location

    if not matched_location:
        return None

    check_in, check_out = _infer_dates_from_text(text)

    adults = None
    rooms = None
    adults_match = _ADULTS_RE.search(text)
    rooms_match = _ROOMS_RE.search(text)
    if adults_match:
        adults = int(adults_match.group(1))
    if rooms_match:
        rooms = int(rooms_match.group(1))

    price_min = None
    price_max = None
    min_match = _PRICE_MIN_RE.search(text)
    max_match = _PRICE_MAX_RE.search(text)
    if min_match:
        price_min = int(min_match.group(1))
    if max_match:
        price_max = int(max_match.group(1))

    between_price_match = _FAST_BETWEEN_PRICE_RE.search(text)
    if between_price_match:
        first = _fast_money_to_int(between_price_match.group(1))
        second = _fast_money_to_int(between_price_match.group(2))
        if first is not None and second is not None:
            price_min = min(first, second)
            price_max = max(first, second)
    else:
        under_price_match = _FAST_UNDER_PRICE_RE.search(text)
        if under_price_match:
            upper = _fast_money_to_int(under_price_match.group(1))
            if upper is not None:
                price_max = upper

        over_price_match = _FAST_OVER_PRICE_RE.search(text)
        if over_price_match:
            lower = _fast_money_to_int(over_price_match.group(1))
            if lower is not None:
                price_min = lower

    if price_min is None and price_max is None and _FILTER_HINT_RE.search(text):
        default_cap = _fast_default_budget_cap(text)
        if default_cap is not None:
            price_max = default_cap

    slots = Slots(
        location=matched_location,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        rooms=rooms,
        price_min=price_min,
        price_max=price_max,
    )

    rating_match = _RATING_RE.search(text)
    star_rating_match = _STAR_RATING_RE.search(text)
    if rating_match:
        setattr(slots, "rating", int(rating_match.group(1)))
    elif star_rating_match:
        setattr(slots, "rating", int(star_rating_match.group(1)))
    else:
        setattr(slots, "rating", None)

    has_local_signal = _contains_any(lowered, HOTEL_WORDS) or "find hotels" in lowered or _has_local_filter_signal(text, slots)
    if has_local_signal and not _DATE_SIGNAL_RE.search(text):
        return EXPLORE_LOCAL, 0.99, slots

    if check_in and check_out:
        return LIVE_PRICES, 0.99, slots

    has_booking_signal = _contains_any(lowered, BOOKING_WORDS)
    if has_booking_signal and not (check_in and check_out):
        return NEEDS_DATES, 0.95, slots

    return None


def _ask_location(intent: str, confidence: float, slots, extra_msg: str = "") -> Dict[str, Any]:
    cities = list(CITY_GEOIDS.keys())
    msg = "Which city/area are you looking for? (e.g. : 'Mirissa', 'Colombo', 'Galle')"
    if extra_msg:
        msg = extra_msg.strip() + " " + msg
    return {
        "intent": intent,
        "confidence": confidence,
        "action": "ASK_LOCATION",
        "message": msg,
        "slots": asdict(slots),
        "choices": cities,
    }


def _ask_dates(intent: str, confidence: float, slots, needs_location_too: bool) -> Dict[str, Any]:
    if needs_location_too:
        msg = "Tell me the city/area AND your check-in + check-out dates."
    else:
        msg = "What are your check-in and check-out dates?"
    return {
        "intent": intent,
        "confidence": confidence,
        "action": "ASK_DATES",
        "message": msg,
        "slots": asdict(slots),
    }


def _rank_and_respond(
    hotels: List[Dict[str, Any]],
    user_query: str,
    mode: str = "text",
    limit: int = 5,
) -> Dict[str, Any]:
    """
    Use LLM to rank hotels and generate a response based on mode.
    
    mode="voice" -> TTS-friendly tone (conversational, short sentences)
    mode="text" -> Normal text tone (can be detailed, formatted)
    """
    if not hotels:
        return {
            "ranked_hotels": [],
            "llm_response": "No hotels found matching your criteria.",
            "mode": mode,
        }
    
    # Limit input to LLM
    hotels_subset = hotels[:15]
    
    # Build tone-specific prompt
    if mode == "voice":
        tone_instruction = """You are a helpful voice assistant. Respond in a natural, conversational tone optimized for text-to-speech:
- Use SHORT sentences
- Avoid special characters, emojis, or formatting
- Sound friendly and natural like you're speaking to someone
- Keep it concise (2-3 sentences max)"""
    else:
        tone_instruction = """You are a helpful hotel search assistant. Respond in a clear, informative text format:
- Use complete sentences with good structure
- You can use formatting if helpful
- Provide helpful details
- Be professional but warm"""
    
    prompt = f"""{tone_instruction}

User Query: "{user_query}"

Hotels available (JSON):
{json.dumps(hotels_subset, indent=2)}

Task:
1. Rank the top {limit} hotels that best match the user's query
2. Return a JSON object with:
   - "ranked_ids": list of hotel IDs in ranked order (top {limit})
   - "response": a natural language response explaining your recommendation

Output only valid JSON, no extra text."""

    try:
        llm_output = generate_text(prompt)
        # Try to parse JSON from LLM response
        # Handle cases where LLM wraps in ```json blocks
        llm_output = llm_output.strip()
        if llm_output.startswith("```json"):
            llm_output = llm_output[7:]
        if llm_output.startswith("```"):
            llm_output = llm_output[3:]
        if llm_output.endswith("```"):
            llm_output = llm_output[:-3]
        llm_output = llm_output.strip()
        
        result = json.loads(llm_output)
        ranked_ids = result.get("ranked_ids", [])
        llm_response = result.get("response", "")
        
        # Reorder hotels based on LLM ranking
        id_to_hotel = {h.get("id"): h for h in hotels}
        ranked_hotels = [id_to_hotel[hid] for hid in ranked_ids if hid in id_to_hotel]
        
        # Add any remaining hotels that weren't ranked
        ranked_hotel_ids = set(ranked_ids)
        for hotel in hotels[:limit]:
            if hotel.get("id") not in ranked_hotel_ids:
                ranked_hotels.append(hotel)
            if len(ranked_hotels) >= limit:
                break
        
        return {
            "ranked_hotels": ranked_hotels[:limit],
            "llm_response": llm_response,
            "mode": mode,
        }
    
    except Exception as e:
        # Fallback: return original order with generic message
        fallback_msg = (
            f"Found {len(hotels)} hotels in your area."
            if mode == "voice"
            else f"Here are {len(hotels)} hotels matching your search criteria."
        )
        return {
            "ranked_hotels": hotels[:limit],
            "llm_response": fallback_msg,
            "mode": mode,
            "llm_error": str(e),
        }


def _generate_local_llm_response(
    hotels: List[Dict[str, Any]],
    location: str,
    user_query: str,
    mode: str,
    limit: int = 3,
) -> str:
    hotels_subset = hotels[:limit]
    compact_hotels = []
    for hotel in hotels_subset:
        compact_hotels.append(
            {
                "name": hotel.get("name") or "Unnamed hotel",
                "rating": hotel.get("rating"),
                "price": hotel.get("price"),
                "location": hotel.get("location") or location,
            }
        )

    tone_instruction = (
        "You are a voice assistant. Reply in 1-2 short natural sentences. "
        "No markdown, no bullet points, no special formatting."
        if mode == "voice"
        else "You are a hotel assistant. Reply in 1-2 concise natural sentences. No markdown or bullet points."
    )

    prompt = f"""{tone_instruction}

User query: {user_query}
Location: {location}
Hotel options: {json.dumps(compact_hotels, ensure_ascii=False)}

Write only the final response text for the user."""

    output = generate_text(prompt, max_output_tokens=90, temperature=0.5)
    return (output or "").strip()


async def _generate_local_llm_response_with_budget(
    hotels: List[Dict[str, Any]],
    location: str,
    user_query: str,
    mode: str,
    timeout_ms: int,
) -> str:
    price_cap = _fast_default_budget_cap(user_query)
    star_match = _STAR_RATING_RE.search(user_query or "")
    rating_floor = int(star_match.group(1)) if star_match else None
    filters: List[str] = []
    if price_cap is not None:
        filters.append(f"budget up to LKR {price_cap:,}")
    if rating_floor is not None:
        filters.append(f"rating {rating_floor}+ stars")

    filter_text = ""
    if filters:
        filter_text = " with " + " and ".join(filters)

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_generate_local_llm_response, hotels, location, user_query, mode),
            timeout=timeout_ms / 1000,
        )
    except asyncio.TimeoutError:
        return f"I found {len(hotels)} hotels in {location}{filter_text}. Tell me if you want me to narrow it further."
    except Exception:
        return f"I found {len(hotels)} hotels in {location}{filter_text}. Tell me if you want me to narrow it further."


async def _rank_and_respond_with_budget(
    hotels: List[Dict[str, Any]],
    user_query: str,
    mode: str,
    timeout_ms: int,
) -> Dict[str, Any]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_rank_and_respond, hotels, user_query, mode),
            timeout=timeout_ms / 1000,
        )
    except asyncio.TimeoutError:
        fallback_msg = (
            f"I found {len(hotels)} live options. Showing best matches now."
            if mode == "voice"
            else f"I found {len(hotels)} live options. Showing the best matches now."
        )
        return {
            "ranked_hotels": hotels[:5],
            "llm_response": fallback_msg,
            "mode": mode,
            "llm_error": f"LLM ranking exceeded {timeout_ms}ms budget",
        }
    except Exception as e:
        fallback_msg = (
            f"I found {len(hotels)} live options."
            if mode == "voice"
            else f"I found {len(hotels)} live options."
        )
        return {
            "ranked_hotels": hotels[:5],
            "llm_response": fallback_msg,
            "mode": mode,
            "llm_error": str(e),
        }


async def handle_query(
    user_query: str,
    mode: str = "text",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Single entry point for text + voice routers.
    
    mode: "text" | "voice" - determines LLM response tone
    """


    req_start = time.perf_counter()
    classify_ms = 0.0
    slot_ms = 0.0

    context_slots = context.get("slots") if isinstance(context, dict) else None
    context_location = None
    if isinstance(context_slots, dict):
        location_value = context_slots.get("location")
        if isinstance(location_value, str):
            context_location = location_value.strip() or None

    fast_result = _try_fast_intent_and_slots(user_query, fallback_location=context_location) # try using regex 
    if fast_result is not None:
        intent, confidence, slots = fast_result
        pred_intent = intent
        classify_ms = round((time.perf_counter() - req_start) * 1000, 2)
    # If regex fails, fall back to ML-based intent prediction and slot extraction
    else:
        classify_start = time.perf_counter()
        pred_intent, confidence = predict_intent(user_query)
        classify_ms = round((time.perf_counter() - classify_start) * 1000, 2)

        slot_start = time.perf_counter()
        slots = extract_slots(user_query)
        slot_ms = round((time.perf_counter() - slot_start) * 1000, 2)
        intent = _apply_overrides(pred_intent, user_query, slots)

    if isinstance(context_slots, dict):
        _apply_context_slots(slots, context_slots)
        intent = _apply_overrides(intent, user_query, slots)

        last_action = context.get("last_action") if isinstance(context, dict) else None

        if (
            last_action in ("LOCAL_DB", "ASK_LOCATION")
            and getattr(slots, "location", None)
            and not (getattr(slots, "check_in", None) and getattr(slots, "check_out", None))
            and (_has_local_filter_signal(user_query, slots) or _is_short_followup(user_query))
        ):
            intent = EXPLORE_LOCAL

        if (
            last_action in ("RAPIDAPI", "ASK_DATES")
            and getattr(slots, "location", None)
            and _is_short_followup(user_query)
            and not (getattr(slots, "check_in", None) and getattr(slots, "check_out", None))
        ):
            intent = NEEDS_DATES

        if (
            getattr(slots, "location", None)
            and not (getattr(slots, "check_in", None) and getattr(slots, "check_out", None))
            and _has_local_filter_signal(user_query, slots)
        ):
            intent = EXPLORE_LOCAL

    # ----------------------------
    # 1) Local exploration (SQLite)
    # ----------------------------
    if intent == EXPLORE_LOCAL:
        if not getattr(slots, "location", None):
            return _ask_location(intent, confidence, slots)

        data = get_hotel_insights_localdb(
            location=slots.location,
            user_request=user_query,
            rating=getattr(slots, "rating", None),
            priceMin=getattr(slots, "price_min", None),
            priceMax=getattr(slots, "price_max", None),
        )
        local_db_ms = round((time.perf_counter() - req_start) * 1000, 2)

        local_results = data.get("results", [])
        local_llm_start = time.perf_counter()
        llm_response = await _generate_local_llm_response_with_budget(
            hotels=local_results,
            location=str(getattr(slots, "location", "")),
            user_query=user_query,
            mode=mode,
            timeout_ms=LOCAL_LLM_BUDGET_MS,
        )
        local_llm_ms = round((time.perf_counter() - local_llm_start) * 1000, 2)

        ranking = {
            "ranked_hotels": local_results[:5],
            "llm_response": llm_response,
            "mode": mode,
            "source": "llm_local",
        }

        data["ranking"] = ranking
        total_ms = round((time.perf_counter() - req_start) * 1000, 2)
        timing = {
            "classify_ms": classify_ms,
            "slot_extract_ms": slot_ms,
            "local_db_ms": local_db_ms,
            "local_llm_ms": local_llm_ms,
            "total_ms": total_ms,
        }
        sla = {
            "route": "LOCAL_DB",
            "target_max_ms": LOCAL_SLA_MS,
            "hit": total_ms <= LOCAL_SLA_MS,
        }

        return {
            "intent": intent,
            "confidence": confidence,
            "action": "LOCAL_DB",
            "slots": asdict(slots),
            "data": data,
            "timing": timing,
            "sla": sla,
        }

    # ----------------------------
    # 2) Needs dates (Maybe location too)
    # ----------------------------
    if intent == NEEDS_DATES:
        needs_location_too = not bool(getattr(slots, "location", None))
        return _ask_dates(intent, confidence, slots, needs_location_too)

    # ----------------------------
    # 3) Live prices (RapidAPI)
    # ----------------------------
    if intent == LIVE_PRICES:
        # Must have dates
        if not (getattr(slots, "check_in", None) and getattr(slots, "check_out", None)):
            return _ask_dates(NEEDS_DATES, confidence, slots, needs_location_too=not bool(getattr(slots, "location", None)))

        # Must have location -> resolve geoId
        if not getattr(slots, "location", None):
            return _ask_location(NEEDS_DATES, confidence, slots, extra_msg="To check live prices,")

        geo = convert_geo_id(slots.location)
        if not geo.geo_id:
            return _ask_location(
                NEEDS_DATES,
                confidence,
                slots,
                extra_msg=f"I couldn't map '{slots.location}' to a supported city.",
            )

        try:
            rapidapi_start = time.perf_counter()
            data = await get_hotel_insights(
                geoId=str(geo.geo_id),
                checkIn=slots.check_in,
                checkOut=slots.check_out,
                adults=getattr(slots, "adults", None) or 2,
                rooms=getattr(slots, "rooms", None) or 1,
                priceMin=getattr(slots, "price_min", None),
                priceMax=getattr(slots, "price_max", None),
                rating=getattr(slots, "rating", None),
                user_request=user_query,
            )
            rapidapi_ms = round((time.perf_counter() - rapidapi_start) * 1000, 2)

            hotels_list = data.get("results", [])
            rank_start = time.perf_counter()
            elapsed_ms = round((time.perf_counter() - req_start) * 1000, 2)
            remaining_budget_ms = RAPIDAPI_SLA_MAX_MS - int(elapsed_ms) - 100
            rank_timeout_ms = min(RAPIDAPI_LLM_BUDGET_MS, max(0, remaining_budget_ms))

            if rank_timeout_ms <= 0:
                ranking = {
                    "ranked_hotels": hotels_list[:5],
                    "llm_response": f"I found {len(hotels_list)} live options. Showing best matches now.",
                    "mode": mode,
                    "llm_error": "Skipped LLM ranking to protect 6s SLA budget",
                }
            else:
                ranking = await _rank_and_respond_with_budget(
                    hotels=hotels_list,
                    user_query=user_query,
                    mode=mode,
                    timeout_ms=rank_timeout_ms,
                )
            rank_ms = round((time.perf_counter() - rank_start) * 1000, 2)
            data["ranking"] = ranking

            total_ms = round((time.perf_counter() - req_start) * 1000, 2)
            timing = {
                "classify_ms": classify_ms,
                "slot_extract_ms": slot_ms,
                "rapidapi_ms": rapidapi_ms,
                "rank_ms": rank_ms,
                "total_ms": total_ms,
            }
            sla = {
                "route": "RAPIDAPI",
                "target_min_ms": RAPIDAPI_SLA_MIN_MS,
                "target_max_ms": RAPIDAPI_SLA_MAX_MS,
                "hit": total_ms <= RAPIDAPI_SLA_MAX_MS,
            }
            logger.info("route=RAPIDAPI total_ms=%.2f sla_hit=%s", total_ms, sla["hit"])

            return {
                "intent": intent,
                "confidence": confidence,
                "action": "RAPIDAPI",
                "slots": asdict(slots),
                "geo": {"geoId": geo.geo_id, "city": geo.matched_city, "reason": geo.reason},
                "data": data,
                "timing": timing,
                "sla": sla,
            }
        except Exception as e:
            error_text = str(e).strip() or type(e).__name__
            total_ms = round((time.perf_counter() - req_start) * 1000, 2)
            timing = {
                "classify_ms": classify_ms,
                "slot_extract_ms": slot_ms,
                "total_ms": total_ms,
            }
            sla = {
                "route": "RAPIDAPI",
                "target_min_ms": RAPIDAPI_SLA_MIN_MS,
                "target_max_ms": RAPIDAPI_SLA_MAX_MS,
                "hit": total_ms <= RAPIDAPI_SLA_MAX_MS,
            }
            logger.warning("route=RAPIDAPI_ERROR total_ms=%.2f error=%s", total_ms, str(e))
            return {
                "intent": intent,
                "confidence": confidence,
                "action": "RAPIDAPI_ERROR",
                "slots": asdict(slots),
                "geo": {"geoId": geo.geo_id, "city": geo.matched_city, "reason": geo.reason},
                "message": f"Sorry, I couldn't fetch live prices right now. Error: {error_text}",
                "error": error_text,
                "timing": timing,
                "sla": sla,
            }

    # ----------------------------
    # 4) Fallback
    # ----------------------------
    return {
        "intent": pred_intent,
        "confidence": confidence,
        "action": "FALLBACK",
        "message": "Sorry, I couldn't understand that request.",
        "slots": asdict(slots),
    }