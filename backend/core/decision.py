from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, List, Tuple

from backend.ml.query_router import predict_intent
from backend.services.keyword_extractor import extract_slots

from backend.services.hotel_insights_localdb import get_hotel_insights_localdb
from backend.services.hotel_insights_rapidapi import get_hotel_insights

from backend.services.location_geoid_converter import convert_geo_id, CITY_GEOIDS
from backend.models import generate_text


# Intention labels
EXPLORE_LOCAL = "EXPLORE_LOCAL"
LIVE_PRICES = "LIVE_PRICES"
NEEDS_DATES = "NEEDS_DATES"


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


async def handle_query(user_query: str, mode: str = "text") -> Dict[str, Any]:
    """
    Single entry point for text + voice routers.
    
    mode: "text" | "voice" - determines LLM response tone
    """
    pred_intent, confidence = predict_intent(user_query)
    slots = extract_slots(user_query)

    intent = _apply_overrides(pred_intent, user_query, slots)

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
        
        # LLM ranking + response
        ranking = _rank_and_respond(
            hotels=data.get("results", []),
            user_query=user_query,
            mode=mode,
        )
        data["ranking"] = ranking

        return {
            "intent": intent,
            "confidence": confidence,
            "action": "LOCAL_DB",
            "slots": asdict(slots),
            "data": data,
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

        data = await get_hotel_insights(
            geoId=str(geo.geo_id),
            checkIn=slots.check_in.isoformat(),
            checkOut=slots.check_out.isoformat(),
            adults=getattr(slots, "adults", None) or 2,
            rooms=getattr(slots, "rooms", None) or 1,
            priceMin=getattr(slots, "price_min", None),
            priceMax=getattr(slots, "price_max", None),
            rating=getattr(slots, "rating", None),
            user_request=user_query,
        )
        
        # LLM ranking + response
        ranking = _rank_and_respond(
            hotels=data.get("results", []),
            user_query=user_query,
            mode=mode,
        )
        data["ranking"] = ranking

        return {
            "intent": intent,
            "confidence": confidence,
            "action": "RAPIDAPI",
            "slots": asdict(slots),
            "geo": {"geoId": geo.geo_id, "city": geo.matched_city, "reason": geo.reason},
            "data": data,
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