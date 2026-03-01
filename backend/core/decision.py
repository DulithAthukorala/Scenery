from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.ml.query_router import predict_intent
from backend.services.keyword_extractor import extract_slots, Slots

from backend.services.hotel_insights_localdb import get_hotel_insights_localdb
from backend.services.hotel_insights_rapidapi import get_hotel_insights

from backend.services.location_geoid_converter import convert_geo_id, CITY_GEOIDS, fuzzy_match_city
from backend.models import generate_text


logger = logging.getLogger(__name__)

# ── Intent labels ──
EXPLORE_LOCAL = "EXPLORE_LOCAL"
LIVE_PRICES = "LIVE_PRICES"
NEEDS_DATES = "NEEDS_DATES"
OFF_TOPIC = "OFF_TOPIC"

# ── Keyword lists for detecting hotel-related queries ──
HOTEL_WORDS = (
    "hotel", "resort", "villa", "guesthouse", "accommodation",
    "stay", "lodge", "hostel", "apartment", "room", "rooms",
    "motel", "inn", "bnb", "b&b", "airbnb",
)

BOOKING_WORDS = (
    "price", "prices", "cost", "rates", "how much",
    "availability", "available", "book", "booking", "reserve",
    "check-in", "check out", "check-out",
    "tonight", "tomorrow", "weekend", "next week", "next month",
)

# ── Regex patterns ──
_DATE_SIGNAL_RE = re.compile(
    r"(\b\d{4}-\d{2}-\d{2}\b|\bcheck[\s-]?in\b|\bcheck[\s-]?out\b|\btonight\b|\btomorrow\b|\bnext week\b|\bnext month\b|\bthis weekend\b)",
    re.IGNORECASE,
)
_NATURAL_DATE_RANGE_RE = re.compile(
    r"\b(?:from\s+)?([a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?)\s+(?:to|until|till|\-)\s+([a-zA-Z]+\s+\d{1,2}(?:st|nd|rd|th)?(?:\s+\d{4})?)\b",
    re.IGNORECASE,
)
_CHECKIN_CHECKOUT_RE = re.compile(
    r"check[\s-]?in\s+(.+?)\s+check[\s-]?out\s+(.+)", re.IGNORECASE,
)
_FAST_BETWEEN_PRICE_RE = re.compile(r"\bbetween\s+([\d.,]+k?)\s+(?:and|to)\s+([\d.,]+k?)\b", re.IGNORECASE)
_FAST_UNDER_PRICE_RE = re.compile(r"\b(?:under|below|less than|up to)\s+([\d.,]+k?)\b", re.IGNORECASE)
_FAST_OVER_PRICE_RE = re.compile(r"\b(?:over|above|more than|at least)\s+([\d.,]+k?)\b(?!\s*star)", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_ADULTS_RE = re.compile(r"(\d+)\s*(adults|adult|people|persons|guests)", re.IGNORECASE)
_ROOMS_RE = re.compile(r"(\d+)\s*(rooms|room)", re.IGNORECASE)
_FILTER_HINT_RE = re.compile(
    r"\b(under|below|less than|up to|above|over|more than|at least|between|budget|cheap|affordable|rating|star|luxury)\b",
    re.IGNORECASE,
)

# ── Off-topic patterns ──
_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|good\s*(morning|afternoon|evening)|greetings|yo|sup|howdy)\s*[!?.]*\s*$",
    re.IGNORECASE,
)
_FAREWELL_RE = re.compile(
    r"^\s*(bye|goodbye|see\s*you|take\s*care|thanks|thank\s*you|cheers|ciao)\s*[!?.]*\s*$",
    re.IGNORECASE,
)
_NON_HOTEL_QUESTION_RE = re.compile(
    r"\b(weather|restaurant|food|eat|flight|train|bus|taxi|museum|temple|church|attraction|visa|currency|recipe|joke|movie|news|sport)\b",
    re.IGNORECASE,
)
_META_QUESTION_RE = re.compile(
    r"\b(who\s+(are|built|made|created)|what\s+(are you|is your name)|how\s+do\s+you\s+work)\b",
    re.IGNORECASE,
)

_MONTH_NAMES = {
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
}


# ═══════════════════════════════════════════════
#  Helper functions
# ═══════════════════════════════════════════════

def _contains_any(text: str, keywords: Tuple[str, ...]) -> bool:
    """Check if any keyword appears in text."""
    t = (text or "").lower()
    return any(k in t for k in keywords)


def _is_off_topic(query: str) -> bool:
    """Return True if the query is clearly not about hotels."""
    q = (query or "").strip()
    if not q:
        return False
    if _GREETING_RE.match(q) or _FAREWELL_RE.match(q) or _META_QUESTION_RE.search(q):
        return True

    has_hotel = _contains_any(q, HOTEL_WORDS)
    has_booking = _contains_any(q, BOOKING_WORDS)
    has_city = any(re.search(rf"\b{re.escape(c.lower())}\b", q.lower()) for c in CITY_GEOIDS)

    if not has_hotel and not has_booking and not has_city and _NON_HOTEL_QUESTION_RE.search(q):
        return True
    return False


def _money_to_int(value: str) -> Optional[int]:
    """Convert strings like '25k', '25000', '25,000' to int."""
    if not value:
        return None
    cleaned = re.sub(r"(lkr|rs\.?|rupees?)\b", "", value.strip().lower().replace(",", ""))
    match = re.search(r"(\d+(?:\.\d+)?)\s*(k)?", cleaned, re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1))
    if match.group(2):
        amount *= 1000
    return int(amount)


def _parse_natural_date(token: str, today: date) -> Optional[date]:
    """Try to parse a human-written date like 'March 20' or '20th March 2026'."""
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", (token or "").strip(), flags=re.IGNORECASE)
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%d %B", "%d %b", "%B %d", "%b %d"):
        try:
            result = datetime.strptime(cleaned.strip(), fmt).date()
            if "%Y" not in fmt:
                result = result.replace(year=today.year)
                if result < today - timedelta(days=30):
                    result = result.replace(year=today.year + 1)
            return result
        except ValueError:
            continue
    return None


def _infer_dates_from_text(text: str) -> tuple[Optional[date], Optional[date]]:
    """Extract check-in / check-out dates from free text."""
    # Try ISO dates first (e.g. 2026-03-20)
    iso_dates = _ISO_DATE_RE.findall(text)
    if len(iso_dates) >= 2:
        try:
            return date.fromisoformat(iso_dates[0]), date.fromisoformat(iso_dates[1])
        except ValueError:
            pass

    today = date.today()

    # "check in March 20 check out March 22"
    m = _CHECKIN_CHECKOUT_RE.search(text or "")
    if m:
        raw_in, raw_out = m.group(1).strip(), m.group(2).strip()
        # try ISO
        try:
            return date.fromisoformat(raw_in), date.fromisoformat(raw_out)
        except ValueError:
            pass
        d_in = _parse_natural_date(raw_in, today)
        d_out = _parse_natural_date(raw_out, today)
        if d_in and d_out:
            if d_out < d_in:
                d_out = d_out.replace(year=d_out.year + 1)
            return d_in, d_out

    # "March 20 to March 22"
    m = _NATURAL_DATE_RANGE_RE.search(text or "")
    if m:
        first = _parse_natural_date(m.group(1), today)
        second = _parse_natural_date(m.group(2), today)
        if first and second:
            if second < first:
                second = second.replace(year=second.year + 1)
            return first, second

    # Shorthand words
    lowered = (text or "").lower()
    if "tonight" in lowered:
        return today, today + timedelta(days=1)
    if "tomorrow" in lowered:
        start = today + timedelta(days=1)
        return start, start + timedelta(days=1)
    if "weekend" in lowered:
        days_until_sat = (5 - today.weekday()) % 7
        start = today + timedelta(days=days_until_sat)
        return start, start + timedelta(days=2)
    if "next week" in lowered:
        start = today + timedelta(days=7)
        return start, start + timedelta(days=2)
    if "next month" in lowered:
        start = today + timedelta(days=30)
        return start, start + timedelta(days=2)

    return None, None


def _apply_overrides(pred_intent: str, query: str, slots) -> str:
    """
    Rule-based corrections on top of ML predictions.
    - If dates exist → LIVE_PRICES
    - If booking words but no dates → NEEDS_DATES
    - If hotel words → EXPLORE_LOCAL
    """
    if pred_intent == OFF_TOPIC:
        return OFF_TOPIC

    if getattr(slots, "check_in", None) and getattr(slots, "check_out", None):
        return LIVE_PRICES

    if _contains_any(query, BOOKING_WORDS):
        return NEEDS_DATES

    if _contains_any(query, HOTEL_WORDS) and pred_intent not in (LIVE_PRICES, NEEDS_DATES):
        return EXPLORE_LOCAL

    return pred_intent


def _apply_context_slots(slots: Slots, context_slots: Dict[str, Any]) -> None:
    """Fill in any missing slot values from conversation context."""
    if not context_slots:
        return

    if not slots.location and context_slots.get("location"):
        slots.location = str(context_slots["location"])

    if not slots.check_in and context_slots.get("check_in"):
        try:
            slots.check_in = date.fromisoformat(str(context_slots["check_in"]))
        except ValueError:
            pass
    if not slots.check_out and context_slots.get("check_out"):
        try:
            slots.check_out = date.fromisoformat(str(context_slots["check_out"]))
        except ValueError:
            pass

    for field in ("adults", "rooms", "price_min", "price_max"):
        if getattr(slots, field, None) is None and context_slots.get(field) is not None:
            try:
                setattr(slots, field, int(context_slots[field]))
            except (ValueError, TypeError):
                pass


# ═══════════════════════════════════════════════
#  Fast regex-based intent + slot extraction
# ═══════════════════════════════════════════════

def _try_fast_intent_and_slots(query: str, fallback_location: Optional[str] = None) -> Tuple[str, float, Slots] | None:
    """
    Try to determine intent and extract slots using regex alone (no ML).
    Returns None if we can't confidently determine the intent.
    """
    text = (query or "").strip()
    lowered = text.lower()
    if not text:
        return None

    # Off-topic check first
    if _is_off_topic(text):
        return OFF_TOPIC, 0.99, Slots()

    # ── Find the city/location ──
    matched_location = None

    # 1) Exact match against known cities
    for city in CITY_GEOIDS:
        if re.search(rf"\b{re.escape(city.lower())}\b", lowered):
            matched_location = city
            break

    # 2) Fuzzy match (handles typos like "Colmbo" → "Colombo")
    if not matched_location:
        matched_location = fuzzy_match_city(text)

    # 3) "in <city>" pattern
    if not matched_location:
        m = re.search(r"\bin\s+([a-zA-Z][a-zA-Z\s]{1,25})", text)
        if m:
            raw = m.group(1).strip(" ,.")
            first_word = raw.split()[0].lower() if raw else ""
            # Don't treat month names or common words as locations
            if first_word not in _MONTH_NAMES and first_word not in ("the", "a", "an", "my", "this", "that", "some", "any"):
                matched_location = fuzzy_match_city(raw) or raw.title()

    # 4) Fall back to location from conversation context
    if not matched_location:
        matched_location = fallback_location

    # If still no location, bail out (let ML handle it)
    if not matched_location:
        return None

    # ── Extract dates ──
    check_in, check_out = _infer_dates_from_text(text)

    # ── Extract adults / rooms ──
    adults_m = _ADULTS_RE.search(text)
    rooms_m = _ROOMS_RE.search(text)
    adults = int(adults_m.group(1)) if adults_m else None
    rooms = int(rooms_m.group(1)) if rooms_m else None

    # ── Extract price range ──
    price_min, price_max = None, None
    between_m = _FAST_BETWEEN_PRICE_RE.search(text)
    if between_m:
        a, b = _money_to_int(between_m.group(1)), _money_to_int(between_m.group(2))
        if a is not None and b is not None:
            price_min, price_max = min(a, b), max(a, b)
    else:
        under_m = _FAST_UNDER_PRICE_RE.search(text)
        if under_m:
            price_max = _money_to_int(under_m.group(1))
        over_m = _FAST_OVER_PRICE_RE.search(text)
        if over_m:
            price_min = _money_to_int(over_m.group(1))

    # ── Build slots ──
    slots = Slots(
        location=matched_location,
        check_in=check_in, check_out=check_out,
        adults=adults, rooms=rooms,
        price_min=price_min, price_max=price_max,
    )

    # ── Decide intent ──
    if check_in and check_out:
        return LIVE_PRICES, 0.99, slots

    if _contains_any(lowered, BOOKING_WORDS):
        return NEEDS_DATES, 0.95, slots

    # Default: local exploration
    return EXPLORE_LOCAL, 0.99, slots


# ═══════════════════════════════════════════════
#  Prompt builders for LLM
# ═══════════════════════════════════════════════

def _rank_and_respond(hotels: List[Dict[str, Any]], user_query: str, mode: str = "text", limit: int = 5) -> Dict[str, Any]:
    """Use LLM to rank hotels and write a natural response."""
    if not hotels:
        return {"ranked_hotels": [], "llm_response": "No hotels found matching your criteria.", "mode": mode}

    hotels_subset = hotels[:15]

    tone = (
        "Reply in a natural conversational tone. Use short sentences. No markdown or emojis."
        if mode == "voice"
        else "Reply in a clear, informative text format. Be professional but warm."
    )

    prompt = f"""{tone}

User Query: "{user_query}"

Hotels available (JSON):
{json.dumps(hotels_subset, indent=2)}

Task:
1. Carefully analyze the user's query for contextual clues:
   - Travel companions (friends, family, solo, couples, business colleagues)
   - Trip purpose (leisure, honeymoon, business, adventure, relaxation)
   - Preferences (luxury, budget, quiet, party atmosphere, romantic, family-friendly)
   - Desired amenities (pool, beach, restaurants, nightlife, activities)
   - Any special requirements or mentioned keywords

2. Rank the top {limit} hotels that best match the user's query and context
   - Prioritize hotels that align with the travel style and purpose
   - Consider price range if mentioned
   - Match amenities to the implied needs (e.g., "friends" = social spaces, "family" = kid-friendly)

3. Return a JSON object with:
   - "ranked_ids": list of hotel IDs in ranked order (top {limit})
   - "response": a natural language response explaining your recommendation

Output only valid JSON, no extra text."""

    try:
        raw = generate_text(prompt).strip()
        # Strip ```json wrapper if present
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]

        result = json.loads(raw.strip())
        ranked_ids = result.get("ranked_ids", [])
        llm_response = result.get("response", "")

        # Reorder hotels by LLM ranking
        id_map = {h.get("id"): h for h in hotels}
        ranked_hotels = [id_map[hid] for hid in ranked_ids if hid in id_map]

        # Pad with unranked hotels if needed
        ranked_set = set(ranked_ids)
        for h in hotels[:limit]:
            if h.get("id") not in ranked_set:
                ranked_hotels.append(h)
            if len(ranked_hotels) >= limit:
                break

        return {"ranked_hotels": ranked_hotels[:limit], "llm_response": llm_response, "mode": mode}

    except Exception as e:
        logger.warning("LLM ranking failed: %s", e)
        return {"ranked_hotels": hotels[:limit], "llm_response": f"Here are {len(hotels)} hotels matching your search.", "mode": mode}


def _generate_local_llm_response(hotels: List[Dict[str, Any]], location: str, user_query: str, mode: str) -> str:
    """Generate a short LLM summary for local DB results."""
    compact = [
        {"name": h.get("name", "Unnamed"), "rating": h.get("rating"), "price": h.get("price"), "location": h.get("location") or location}
        for h in hotels[:3]
    ]

    tone = (
        "You are a voice assistant. Reply in 1-2 short natural sentences. No markdown."
        if mode == "voice"
        else "You are a hotel assistant. Reply in 1-2 concise sentences. No markdown."
    )
    prompt = f"""{tone}

User query: {user_query}
Location: {location}
Hotel options: {json.dumps(compact, ensure_ascii=False)}

Write only the final response text for the user."""

    output = generate_text(prompt, max_output_tokens=90, temperature=0.5)
    return (output or "").strip()


# ═══════════════════════════════════════════════
#  Prompt helpers (ask user for missing info)
# ═══════════════════════════════════════════════

def _ask_location(intent: str, confidence: float, slots, extra_msg: str = "") -> Dict[str, Any]:
    msg = "Which city/area are you looking for? (e.g. : 'Mirissa', 'Colombo', 'Galle')"
    if extra_msg:
        msg = extra_msg.strip() + " " + msg
    return {
        "intent": intent, "confidence": confidence, "action": "ASK_LOCATION",
        "message": msg, "slots": asdict(slots), "choices": list(CITY_GEOIDS.keys()),
    }


def _ask_dates(intent: str, confidence: float, slots, needs_location_too: bool) -> Dict[str, Any]:
    msg = "Tell me the city/area AND your check-in + check-out dates." if needs_location_too \
        else "What are your check-in and check-out dates?"
    return {"intent": intent, "confidence": confidence, "action": "ASK_DATES", "message": msg, "slots": asdict(slots)}


# ═══════════════════════════════════════════════
#  Main entry point
# ═══════════════════════════════════════════════

async def handle_query(
    user_query: str,
    mode: str = "text",
    force_mode: Optional[str] = None,
    preset_location: Optional[str] = None,
    preset_dates: Optional[dict] = None,
    rerank_hotels: Optional[list] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Single entry point for all chat / voice queries.
    Routes to: OFF_TOPIC → EXPLORE_LOCAL → NEEDS_DATES → LIVE_PRICES
    
    If rerank_hotels is provided, skips RapidAPI call and just re-ranks those hotels.
    """
    # Re-ranking mode: Just re-rank existing hotels without calling RapidAPI
    if rerank_hotels and isinstance(rerank_hotels, list) and len(rerank_hotels) > 0:
        ranking = await asyncio.to_thread(_rank_and_respond, rerank_hotels, user_query, mode)
        return {
            "intent": "LIVE_PRICES", "confidence": 1.0, "action": "RERANK",
            "slots": {"location": preset_location or ""} if preset_location else {},
            "data": {"ranking": ranking},
        }
    
    # Live mode with presets from date picker form
    if force_mode == "live_prices" and preset_dates:
        check_in = preset_dates.get("check_in")
        check_out = preset_dates.get("check_out")
        location = preset_location or ""
        
        if not (check_in and check_out and location):
            return {
                "intent": "LIVE_PRICES", "confidence": 1.0, "action": "FALLBACK",
                "message": "Please select a city and dates in the Live Prices form.",
                "slots": {}
            }
        
        # Extract preferences from query
        extracted = extract_slots(user_query)
        slots = Slots(
            location=location,
            check_in=check_in,
            check_out=check_out,
            price_min=getattr(extracted, "price_min", None),
            price_max=getattr(extracted, "price_max", None),
            adults=getattr(extracted, "adults", None) or 2,
            rooms=getattr(extracted, "rooms", None) or 1,
        )
        
        geo = convert_geo_id(location)
        if not geo.geo_id:
            return {
                "intent": "LIVE_PRICES", "confidence": 1.0, "action": "FALLBACK",
                "message": f"Sorry, I couldn't map '{location}' to a supported city.",
                "slots": asdict(slots)
            }
        
        try:
            data = await get_hotel_insights(
                geoId=str(geo.geo_id),
                checkIn=check_in,
                checkOut=check_out,
                adults=slots.adults,
                rooms=slots.rooms,
                priceMin=slots.price_min,
                priceMax=slots.price_max,
                rating=None,
                user_request=user_query,
            )
            hotels_list = data.get("results", [])
            ranking = await asyncio.to_thread(_rank_and_respond, hotels_list, user_query, mode)
            data["ranking"] = ranking
            
            return {
                "intent": "LIVE_PRICES", "confidence": 1.0, "action": "RAPIDAPI",
                "slots": asdict(slots),
                "geo": {"geoId": geo.geo_id, "city": geo.matched_city},
                "data": data,
            }
        except Exception as e:
            logger.warning("RapidAPI error: %s", e)
            return {
                "intent": "LIVE_PRICES", "confidence": 1.0, "action": "RAPIDAPI_ERROR",
                "message": f"Sorry, I couldn't fetch live prices right now. Error: {e}",
                "slots": asdict(slots),
            }
    
    context_slots = context.get("slots") if isinstance(context, dict) else None
    context_location = None
    if isinstance(context_slots, dict) and context_slots.get("location"):
        context_location = str(context_slots["location"]).strip() or None

    # ── Step 1: Try fast regex-based classification ──
    fast = _try_fast_intent_and_slots(user_query, fallback_location=context_location)

    if fast:
        intent, confidence, slots = fast
    else:
        # Fall back to ML model + spaCy slot extraction
        intent, confidence = predict_intent(user_query)
        slots = extract_slots(user_query)
        intent = _apply_overrides(intent, user_query, slots)

    # ── Step 2: Merge in context from previous turns ──
    if isinstance(context_slots, dict):
        _apply_context_slots(slots, context_slots)
        intent = _apply_overrides(intent, user_query, slots)

    # Mode override: Standard mode never uses RapidAPI
    if force_mode == "standard" and intent == LIVE_PRICES:
        intent = EXPLORE_LOCAL

    # ── Step 3: Route by intent ──

    # 0) Off-topic
    if intent == OFF_TOPIC:
        if _GREETING_RE.search(user_query):
            msg = (
                "Hello! I'm Scenery, your Sri Lanka hotel assistant. "
                "Ask me things like 'Hotels in Colombo' or 'Luxury stays in Ella under 30000 LKR'. "
                "How can I help?"
            )
        elif _FAREWELL_RE.search(user_query):
            msg = "Goodbye! Have a wonderful trip. Come back anytime you need hotel help."
        else:
            msg = (
                "I'm specialised in Sri Lanka hotel search. "
                "Try asking something like 'Hotels in Kandy' or 'Best places to stay in Mirissa under 20000 LKR'."
            )
        return {"intent": OFF_TOPIC, "confidence": confidence, "action": "FALLBACK", "message": msg, "slots": asdict(slots)}

    # 1) Local exploration (SQLite)
    if intent == EXPLORE_LOCAL:
        if not getattr(slots, "location", None):
            return _ask_location(intent, confidence, slots)

        data = get_hotel_insights_localdb(
            location=slots.location,
            user_request=user_query,
            rating=None,
            priceMin=getattr(slots, "price_min", None),
            priceMax=getattr(slots, "price_max", None),
        )
        results = data.get("results", [])

        # Use LLM to rank hotels by user preferences (same as LIVE_PRICES mode)
        ranking = await asyncio.to_thread(_rank_and_respond, results, user_query, mode)
        data["ranking"] = ranking

        return {"intent": intent, "confidence": confidence, "action": "LOCAL_DB", "slots": asdict(slots), "data": data}

    # 2) Needs dates
    if intent == NEEDS_DATES:
        return _ask_dates(intent, confidence, slots, needs_location_too=not bool(getattr(slots, "location", None)))

    # 3) Live prices (RapidAPI)
    if intent == LIVE_PRICES:
        if not (getattr(slots, "check_in", None) and getattr(slots, "check_out", None)):
            return _ask_dates(NEEDS_DATES, confidence, slots, needs_location_too=not bool(getattr(slots, "location", None)))

        if not getattr(slots, "location", None):
            return _ask_location(NEEDS_DATES, confidence, slots, extra_msg="To check live prices,")

        geo = convert_geo_id(slots.location)
        if not geo.geo_id:
            return _ask_location(NEEDS_DATES, confidence, slots, extra_msg=f"I couldn't map '{slots.location}' to a supported city.")

        try:
            data = await get_hotel_insights(
                geoId=str(geo.geo_id),
                checkIn=slots.check_in,
                checkOut=slots.check_out,
                adults=getattr(slots, "adults", None) or 2,
                rooms=getattr(slots, "rooms", None) or 1,
                priceMin=getattr(slots, "price_min", None),
                priceMax=getattr(slots, "price_max", None),
                rating=None,
                user_request=user_query,
            )
            hotels_list = data.get("results", [])
            ranking = await asyncio.to_thread(_rank_and_respond, hotels_list, user_query, mode)
            data["ranking"] = ranking

            return {
                "intent": intent, "confidence": confidence, "action": "RAPIDAPI",
                "slots": asdict(slots),
                "geo": {"geoId": geo.geo_id, "city": geo.matched_city},
                "data": data,
            }
        except Exception as e:
            logger.warning("RapidAPI error: %s", e)
            return {
                "intent": intent, "confidence": confidence, "action": "RAPIDAPI_ERROR",
                "slots": asdict(slots),
                "geo": {"geoId": geo.geo_id, "city": geo.matched_city},
                "message": f"Sorry, I couldn't fetch live prices right now. Error: {e}",
            }

    # 4) Fallback
    return {
        "intent": intent, "confidence": confidence, "action": "FALLBACK",
        "message": "I'm not sure what you're looking for. Try something like 'Hotels in Galle' or 'Luxury stays in Colombo'.",
        "slots": asdict(slots),
    }