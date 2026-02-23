"""
This module contains the core decision logic
- Takes user queries as input
- Predicts intent and extracts slots
- Routes to the appropriate data source (local DB or RapidAPI) based on intent and slot completeness
- Returns a structured JSON dict for the frontend to consume
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from backend.ml.query_router import predict_intent
from backend.services.keyword_extractor import extract_slots


from backend.services.hotel_insights_localdb import get_hotel_insights_localdb
from backend.services.hotel_insights_rapidapi import get_hotel_insights


# Intent labels
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


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def _apply_overrides(pred_intent: str, query: str, slots) -> str:
    """
    Rule layer to stabilize TF-IDF mistakes.
    """
    has_hotel_signal = _contains_any(query, HOTEL_WORDS)
    has_booking_signal = _contains_any(query, BOOKING_WORDS)

    # If dates are explicit -> LIVE_PRICES
    if slots.check_in and slots.check_out:
        return LIVE_PRICES

    # If booking/price/availability intent but missing exact dates -> NEEDS_DATES
    if has_booking_signal and not (slots.check_in and slots.check_out):
        return NEEDS_DATES

    # If it's clearly hotel-related, never fall into OUT_OF_SCOPE-like behavior
    if has_hotel_signal and pred_intent not in (LIVE_PRICES, NEEDS_DATES):
        return EXPLORE_LOCAL

    return pred_intent


async def handle_query(user_query: str) -> Dict[str, Any]:
    """
    Single entry point for your routers.
    Returns a structured JSON dict for the frontend.
    """
    pred_intent, confidence = predict_intent(user_query)
    slots = extract_slots(user_query)

    intent = _apply_overrides(pred_intent, user_query, slots)

    # ---- Route ----
    if intent == EXPLORE_LOCAL:
        if not slots.location:
            return {
                "intent": intent,
                "confidence": confidence,
                "action": "ASK_LOCATION",
                "message": "Which city/area in Sri Lanka are you looking for? (e.g., Galle, Colombo, Ella)",
                "slots": asdict(slots),
            }

        data = get_hotel_insights_localdb(location=slots.location, user_request=user_query)
        return {
            "intent": intent,
            "confidence": confidence,
            "action": "LOCAL_DB",
            "slots": asdict(slots),
            "data": data,
        }

    if intent == NEEDS_DATES:
        # Optionally: if location exists, you can also return local DB suggestions alongside asking dates.
        msg = "What are your check-in and check-out dates?"
        if not slots.location:
            msg = "Which city/area, and what are your check-in and check-out dates?"

        return {
            "intent": intent,
            "confidence": confidence,
            "action": "ASK_DATES",
            "message": msg,
            "slots": asdict(slots),
        }

    if intent == LIVE_PRICES:
        # Must have dates; if not, downgrade to NEEDS_DATES
        if not (slots.check_in and slots.check_out):
            return {
                "intent": NEEDS_DATES,
                "confidence": confidence,
                "action": "ASK_DATES",
                "message": "What are your check-in and check-out dates?",
                "slots": asdict(slots),
            }

        if not slots.location:
            return {
                "intent": NEEDS_DATES,
                "confidence": confidence,
                "action": "ASK_LOCATION",
                "message": "Which city/area should I check prices for? (e.g., Galle, Colombo, Ella)",
                "slots": asdict(slots),
            }

        data = await get_hotel_insights(
            location=slots.location,
            checkIn=slots.check_in.isoformat(),
            checkOut=slots.check_out.isoformat(),
            adults=slots.adults or 2,
            rooms=slots.rooms or 1,
            priceMin=slots.price_min,
            priceMax=slots.price_max,
            user_request=user_query,
        )
        return {
            "intent": intent,
            "confidence": confidence,
            "action": "RAPIDAPI",
            "slots": asdict(slots),
            "data": data,
        }

    # Fallback (should be rare after overrides)
    return {
        "intent": pred_intent,
        "confidence": confidence,
        "action": "FALLBACK",
        "message": "Sorry, I couldn't understand that request.",
        "slots": asdict(slots),
    }
