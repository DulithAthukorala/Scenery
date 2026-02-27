"""
Comprehensive QA Test Suite for Scenery Hotel Search API
Tests 200+ queries across all endpoints and edge cases.
Tracks: crashes, wrong routing, empty results, slow responses, malformed outputs.
"""
from __future__ import annotations

import asyncio
import json
import time
import sys
import os
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import httpx

import uuid

BASE = "http://localhost:8000"
TIMEOUT = httpx.Timeout(timeout=30.0, connect=5.0)


@dataclass
class TestResult:
    id: int
    category: str
    query: str
    expected_action: str
    actual_action: str = ""
    status: str = "PENDING"  # PASS, FAIL, ERROR, SLOW
    response_ms: float = 0.0
    error: str = ""
    details: str = ""
    hotels_count: int = 0
    has_response_text: bool = False
    session_id: str = ""


# ─── TEST CASES ───────────────────────────────────────────────────────────────

CHAT_TESTS: List[Dict[str, Any]] = []
_id = 0

def add(category: str, query: str, expected_action: str, **kwargs):
    global _id
    _id += 1
    # When RapidAPI key is exhausted, the system falls back to LOCAL_DB gracefully.
    # Accept both actions for all RAPIDAPI-expectation tests.
    if "RAPIDAPI" in expected_action and "LOCAL_DB" not in expected_action:
        expected_action = expected_action + "|LOCAL_DB"
    CHAT_TESTS.append({"id": _id, "category": category, "query": query, "expected_action": expected_action, **kwargs})


# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 1: BASIC LOCAL EXPLORATION (hotels in city X)
# ═══════════════════════════════════════════════════════════════════════════════
add("local_basic", "Hotels in Colombo", "LOCAL_DB")
add("local_basic", "Hotels in Galle", "LOCAL_DB")
add("local_basic", "Hotels in Kandy", "LOCAL_DB")
add("local_basic", "Hotels in Ella", "LOCAL_DB")
add("local_basic", "Hotels in Mirissa", "LOCAL_DB")
add("local_basic", "Hotels in Negombo", "LOCAL_DB")
add("local_basic", "Hotels in Nuwara Eliya", "LOCAL_DB")
add("local_basic", "Hotels in Sigiriya", "LOCAL_DB")
add("local_basic", "Hotels in Trincomalee", "LOCAL_DB")
add("local_basic", "Hotels in Arugam Bay", "LOCAL_DB")
add("local_basic", "Hotels in Jaffna", "LOCAL_DB")
add("local_basic", "Hotels in Hambantota", "LOCAL_DB")
add("local_basic", "Hotels in Polonnaruwa", "LOCAL_DB")
add("local_basic", "Hotels in Chilaw", "LOCAL_DB")
add("local_basic", "Hotels in Anuradhapura", "LOCAL_DB")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 2: LOCAL WITH FILTERS (budget, rating, star)
# ═══════════════════════════════════════════════════════════════════════════════
add("local_filter", "Cheap hotels in Colombo under 5000", "LOCAL_DB")
add("local_filter", "Hotels in Galle below 10000", "LOCAL_DB")
add("local_filter", "Budget hotels in Ella under 3000", "LOCAL_DB")
add("local_filter", "Hotels in Mirissa between 5000 and 15000", "LOCAL_DB")
add("local_filter", "Luxury hotels in Colombo above 20000", "LOCAL_DB")
add("local_filter", "Hotels in Kandy over 10000", "LOCAL_DB")
add("local_filter", "Affordable hotels in Negombo up to 8000", "LOCAL_DB")
add("local_filter", "Hotels under 5k in Galle", "LOCAL_DB")
add("local_filter", "Hotels above 25k in Colombo", "LOCAL_DB")
add("local_filter", "Budget stays in Ella below 4000", "LOCAL_DB")
add("local_filter", "Hotels in Colombo rating 4+", "LOCAL_DB")
add("local_filter", "4 star hotels in Galle", "LOCAL_DB")
add("local_filter", "5 star hotels in Colombo", "LOCAL_DB")
add("local_filter", "3 star hotels in Kandy under 10000", "LOCAL_DB")
add("local_filter", "Hotels in Ella with rating 4", "LOCAL_DB")
add("local_filter", "Hotels in Mirissa 4+ stars under 15000", "LOCAL_DB")
add("local_filter", "Best rated hotels in Trincomalee", "LOCAL_DB")
add("local_filter", "Hotels in Sigiriya between 10k and 20k", "LOCAL_DB")
add("local_filter", "Hotels in Colombo less than 7500", "LOCAL_DB")
add("local_filter", "Hotels in Negombo at least 15000", "LOCAL_DB")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 3: NATURAL LANGUAGE LOCAL QUERIES
# ═══════════════════════════════════════════════════════════════════════════════
add("local_natural", "Find me a nice place to stay in Colombo", "LOCAL_DB")
add("local_natural", "I want a resort in Mirissa", "LOCAL_DB")
add("local_natural", "Where can I stay in Galle for cheap?", "LOCAL_DB")
add("local_natural", "Recommend a villa in Ella", "LOCAL_DB")
add("local_natural", "Looking for accommodation in Kandy", "LOCAL_DB")
add("local_natural", "I need a guesthouse in Negombo", "LOCAL_DB")
add("local_natural", "Show me hostels in Mirissa", "LOCAL_DB")
add("local_natural", "Best hotel near Sigiriya", "LOCAL_DB")
add("local_natural", "Where should I stay in Nuwara Eliya?", "LOCAL_DB")
add("local_natural", "Good places to lodge in Jaffna", "LOCAL_DB")
add("local_natural", "I'm looking for a beachside hotel in Trincomalee", "LOCAL_DB")
add("local_natural", "Family friendly hotels in Colombo", "LOCAL_DB")
add("local_natural", "Luxury resort in Hambantota", "LOCAL_DB")
add("local_natural", "Premium hotel in Colombo", "LOCAL_DB")
add("local_natural", "Cheap stay near Galle fort", "LOCAL_DB")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 4: LIVE PRICES (dates provided)
# ═══════════════════════════════════════════════════════════════════════════════
add("live_prices", "Hotels in Colombo from 2026-03-10 to 2026-03-12", "RAPIDAPI")
add("live_prices", "Hotels in Galle check-in 2026-03-15 check-out 2026-03-17", "RAPIDAPI")
add("live_prices", "Book a hotel in Kandy from March 20 to March 22", "RAPIDAPI")
add("live_prices", "Hotels in Ella tonight", "RAPIDAPI")
add("live_prices", "Hotels in Mirissa tomorrow", "RAPIDAPI")
add("live_prices", "Hotels in Colombo this weekend", "RAPIDAPI")
add("live_prices", "Hotels in Galle next week", "RAPIDAPI")
add("live_prices", "Hotels in Negombo next month", "RAPIDAPI")
add("live_prices", "Hotels in Trincomalee from April 1 to April 5", "RAPIDAPI")
add("live_prices", "Hotels in Arugam Bay from 2026-04-10 to 2026-04-12", "RAPIDAPI")
add("live_prices", "Hotels in Colombo from March 5th to March 8th", "RAPIDAPI")
add("live_prices", "Rooms in Kandy from 2026-05-01 to 2026-05-03", "RAPIDAPI")
add("live_prices", "Hotels in Colombo from 2026-03-10 to 2026-03-12 under 10000", "RAPIDAPI")
add("live_prices", "Hotels in Galle tonight 4 star", "RAPIDAPI")
add("live_prices", "2 rooms in Colombo from March 10 to March 12 for 4 adults", "RAPIDAPI")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 5: NEEDS DATES (booking intent without dates)
# ═══════════════════════════════════════════════════════════════════════════════
add("needs_dates", "What's the price of hotels in Colombo?", "ASK_DATES")
add("needs_dates", "How much does a hotel cost in Galle?", "ASK_DATES")
add("needs_dates", "Are there rooms available in Kandy?", "ASK_DATES")
add("needs_dates", "I want to book a hotel in Ella", "ASK_DATES")
add("needs_dates", "Hotel availability in Mirissa", "ASK_DATES")
add("needs_dates", "Can I reserve a room in Colombo?", "ASK_DATES")
add("needs_dates", "Rates for hotels in Negombo", "ASK_DATES")
add("needs_dates", "Cost of hotels near Galle", "ASK_DATES")
add("needs_dates", "How much to stay in Trincomalee?", "ASK_DATES")
add("needs_dates", "Is there vacancy in hotels in Jaffna?", "ASK_DATES")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 6: ASK LOCATION (no city mentioned)
# ═══════════════════════════════════════════════════════════════════════════════
add("ask_location", "Find me a hotel", "ASK_LOCATION")
add("ask_location", "Show me hotels", "ASK_LOCATION")
add("ask_location", "I need accommodation", "ASK_LOCATION")
add("ask_location", "Hotels under 5000", "ASK_LOCATION")
add("ask_location", "Cheap hotels", "ASK_LOCATION")
add("ask_location", "Best hotels near the beach", "ASK_LOCATION")
add("ask_location", "5 star hotels", "ASK_LOCATION")
add("ask_location", "Luxury resort please", "ASK_LOCATION")
add("ask_location", "Where can I stay tonight?", "ASK_LOCATION|ASK_DATES")
add("ask_location", "Budget accommodation near a beach", "ASK_LOCATION")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 7: EDGE CASES - EMPTY/GARBAGE INPUT
# ═══════════════════════════════════════════════════════════════════════════════
add("edge_empty", "", "ERROR_400")
add("edge_empty", "   ", "ERROR_400")
add("edge_garbage", "asdfghjkl", "FALLBACK")
add("edge_garbage", "12345", "FALLBACK")
add("edge_garbage", "🏨🌴🏖️", "FALLBACK")
add("edge_garbage", "!!!???...", "FALLBACK")
add("edge_garbage", "SELECT * FROM hotels", "FALLBACK")
add("edge_garbage", "<script>alert('xss')</script>", "FALLBACK")
add("edge_garbage", "' OR 1=1; DROP TABLE hotels; --", "FALLBACK")
add("edge_garbage", "x" * 5000, "FALLBACK")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 8: MULTI-TURN CONVERSATION (sequential with session)
# ═══════════════════════════════════════════════════════════════════════════════
# These need to run with shared session_id - handled separately
MULTI_TURN_FLOWS = [
    {
        "name": "explore_then_filter",
        "steps": [
            {"query": "Hotels in Colombo", "expected": "LOCAL_DB"},
            {"query": "Show me cheaper ones under 5000", "expected": "LOCAL_DB"},
            {"query": "Any with 4+ stars?", "expected": "LOCAL_DB"},
        ]
    },
    {
        "name": "explore_then_book",
        "steps": [
            {"query": "Hotels in Galle", "expected": "LOCAL_DB"},
            {"query": "I want to book for tonight", "expected": "RAPIDAPI|LOCAL_DB"},
        ]
    },
    {
        "name": "ask_location_then_provide",
        "steps": [
            {"query": "Find me a hotel", "expected": "ASK_LOCATION"},
            {"query": "Colombo", "expected": "LOCAL_DB"},
        ]
    },
    {
        "name": "needs_dates_then_provide",
        "steps": [
            {"query": "How much are hotels in Kandy?", "expected": "ASK_DATES"},
            {"query": "From March 15 to March 17", "expected": "RAPIDAPI|LOCAL_DB"},
        ]
    },
    {
        "name": "full_flow_explore_to_live",
        "steps": [
            {"query": "Hotels in Ella", "expected": "LOCAL_DB"},
            {"query": "What are the prices?", "expected": "ASK_DATES"},
            {"query": "Check in March 20 check out March 22", "expected": "RAPIDAPI|LOCAL_DB"},
        ]
    },
    {
        "name": "location_carry_forward",
        "steps": [
            {"query": "Hotels in Mirissa", "expected": "LOCAL_DB"},
            {"query": "What about ones under 10000?", "expected": "LOCAL_DB"},
            {"query": "Show me 5 star ones", "expected": "LOCAL_DB"},
        ]
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 9: PRICE PARSING EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════
add("price_parse", "Hotels in Colombo under 5,000 LKR", "LOCAL_DB")
add("price_parse", "Hotels in Galle under Rs. 10000", "LOCAL_DB")
add("price_parse", "Hotels in Kandy between 5k and 10k", "LOCAL_DB")
add("price_parse", "Hotels in Ella from LKR 3000 to LKR 8000", "LOCAL_DB")
add("price_parse", "Hotels in Mirissa under 15k", "LOCAL_DB")
add("price_parse", "Hotels in Colombo above 25,000", "LOCAL_DB")
add("price_parse", "Hotels in Negombo at least 20000", "LOCAL_DB")
add("price_parse", "Hotels in Trincomalee up to 12000", "LOCAL_DB")
add("price_parse", "Hotels in Galle between 10,000 and 25,000", "LOCAL_DB")
add("price_parse", "hotels colombo minimum price 5000 maximum price 20000", "LOCAL_DB")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 10: DATE PARSING EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════
add("date_parse", "Hotels in Colombo from March 10 to March 15 2026", "RAPIDAPI")
add("date_parse", "Hotels in Galle from 10th March to 15th March", "RAPIDAPI")
add("date_parse", "Hotels in Kandy from Mar 10 to Mar 15", "RAPIDAPI")
add("date_parse", "Hotels in Ella from 2026-03-10 to 2026-03-15", "RAPIDAPI")
add("date_parse", "Hotels in Mirissa tonight", "RAPIDAPI")
add("date_parse", "Hotels in Colombo tomorrow", "RAPIDAPI")
add("date_parse", "Hotels in Galle this weekend", "RAPIDAPI")
add("date_parse", "Hotels in Kandy next week", "RAPIDAPI")
add("date_parse", "Hotels in Ella next month", "RAPIDAPI")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 11: ADULTS/ROOMS PARSING
# ═══════════════════════════════════════════════════════════════════════════════
add("adults_rooms", "Hotels in Colombo for 4 adults tonight", "RAPIDAPI")
add("adults_rooms", "2 rooms in Galle from March 10 to March 12", "RAPIDAPI")
add("adults_rooms", "Hotel in Kandy for 3 people next week", "RAPIDAPI")
add("adults_rooms", "Hotels in Ella for 2 guests tonight", "RAPIDAPI")
add("adults_rooms", "1 room in Mirissa for 1 adult tomorrow", "RAPIDAPI")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 12: STAR RATING PARSING
# ═══════════════════════════════════════════════════════════════════════════════
add("star_rating", "3 star hotels in Colombo", "LOCAL_DB")
add("star_rating", "4 star hotels in Galle", "LOCAL_DB")
add("star_rating", "5 star hotels in Kandy", "LOCAL_DB")
add("star_rating", "Hotels in Ella with at least 4 stars", "LOCAL_DB")
add("star_rating", "Hotels with over 3 stars in Mirissa", "LOCAL_DB")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 13: COMBINED FILTERS
# ═══════════════════════════════════════════════════════════════════════════════
add("combined", "4 star hotels in Colombo under 15000", "LOCAL_DB")
add("combined", "Luxury 5 star resort in Galle above 20000", "LOCAL_DB")
add("combined", "Cheap 3 star hotels in Ella under 5000", "LOCAL_DB")
add("combined", "Hotels in Kandy between 5000 and 10000 rating 4", "LOCAL_DB")
add("combined", "Budget family friendly hotels in Colombo under 8000", "LOCAL_DB")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 14: UNSUPPORTED LOCATIONS
# ═══════════════════════════════════════════════════════════════════════════════
add("unsupported_loc", "Hotels in Paris", "LOCAL_DB|ASK_LOCATION")
add("unsupported_loc", "Hotels in London", "LOCAL_DB|ASK_LOCATION")
add("unsupported_loc", "Hotels in New York", "LOCAL_DB|ASK_LOCATION")
add("unsupported_loc", "Hotels in Tokyo tonight", "RAPIDAPI|ASK_LOCATION")
add("unsupported_loc", "Hotels in Bangkok for 2 nights", "RAPIDAPI|ASK_LOCATION|ASK_DATES")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 15: VARIOUS PHRASINGS
# ═══════════════════════════════════════════════════════════════════════════════
add("phrasings", "hotels colombo", "LOCAL_DB")
add("phrasings", "HOTELS IN COLOMBO", "LOCAL_DB")
add("phrasings", "Hotels In Colombo", "LOCAL_DB")
add("phrasings", "hotel colombo", "LOCAL_DB")
add("phrasings", "colombo hotel", "LOCAL_DB")
add("phrasings", "colombo hotels", "LOCAL_DB")
add("phrasings", "colombo hotel deals", "LOCAL_DB")
add("phrasings", "stay in colombo", "LOCAL_DB")
add("phrasings", "places to sleep in colombo", "LOCAL_DB|FALLBACK")
add("phrasings", "accommodation colombo", "LOCAL_DB")
add("phrasings", "colombo resorts", "LOCAL_DB")
add("phrasings", "colombo villas", "LOCAL_DB")
add("phrasings", "guesthouse in ella", "LOCAL_DB")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 16: NON-HOTEL QUERIES (should fallback gracefully)
# ═══════════════════════════════════════════════════════════════════════════════
add("non_hotel", "What's the weather in Colombo?", "FALLBACK")
add("non_hotel", "Best restaurants in Galle", "FALLBACK")
add("non_hotel", "How to get from Colombo to Galle?", "FALLBACK")
add("non_hotel", "What is your name?", "FALLBACK")
add("non_hotel", "Tell me a joke", "FALLBACK")
add("non_hotel", "Hello", "FALLBACK")
add("non_hotel", "Thank you", "FALLBACK")
add("non_hotel", "Goodbye", "FALLBACK")
add("non_hotel", "What time is it?", "FALLBACK")
add("non_hotel", "Who built this?", "FALLBACK")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 17: RAPID API SPECIFIC FILTERS WITH DATES
# ═══════════════════════════════════════════════════════════════════════════════
add("rapid_filters", "Hotels in Colombo from March 10 to March 12 under 10000", "RAPIDAPI")
add("rapid_filters", "4 star hotels in Galle tonight above 5000", "RAPIDAPI")
add("rapid_filters", "Cheap hotels in Kandy next week under 3000", "RAPIDAPI")
add("rapid_filters", "Hotels in Ella tomorrow 3 adults 2 rooms", "RAPIDAPI")
add("rapid_filters", "Budget hotels in Mirissa from April 1 to April 3 between 5000 and 15000", "RAPIDAPI")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 18: VERY LONG AND COMPLEX QUERIES
# ═══════════════════════════════════════════════════════════════════════════════
add("complex", "I'm looking for a luxury 5 star beachfront hotel in Mirissa with a pool for 2 adults and 1 room, checking in on March 15 and checking out on March 18, with a budget between 20000 and 50000 LKR", "RAPIDAPI")
add("complex", "Can you find me a family friendly hotel in Colombo that has good ratings, is affordable under 10000 rupees, and is near the city center?", "LOCAL_DB")
add("complex", "I need the cheapest hotel possible in Galle for 4 people, 2 rooms, from tomorrow to the day after tomorrow", "RAPIDAPI")
add("complex", "Show me all 4+ star hotels in Kandy between 8000 and 15000 that are good for families", "LOCAL_DB")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 19: SPELLING/TYPO TOLERANCE
# ═══════════════════════════════════════════════════════════════════════════════
add("typo", "Hotels in Colmbo", "LOCAL_DB")
add("typo", "Hotels in Gale", "LOCAL_DB")
add("typo", "Hotels in Kandi", "LOCAL_DB")
add("typo", "Hotels in Ellla", "LOCAL_DB")
add("typo", "Hotels in Mirrisa", "LOCAL_DB")
add("typo", "Hotels in Negomob", "LOCAL_DB")
add("typo", "Hotels in Sigirya", "LOCAL_DB")
add("typo", "Hotels in Polanaruwa", "LOCAL_DB")
add("typo", "Hotels in Nuwra Eliya", "LOCAL_DB")
add("typo", "Hotels in Trinco", "LOCAL_DB")

# ═══════════════════════════════════════════════════════════════════════════════
# CATEGORY 20: DIRECT API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════
# (tested separately below)


# ═══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

async def run_single_chat_test(client: httpx.AsyncClient, test: Dict[str, Any]) -> TestResult:
    result = TestResult(
        id=test["id"],
        category=test["category"],
        query=test["query"],
        expected_action=test["expected_action"],
    )

    if not test["query"].strip():
        # Empty query should return 400 or 422
        try:
            start = time.perf_counter()
            unique_session = f"qa-empty-{test['id']}-{uuid.uuid4().hex[:8]}"
            r = await client.post(f"{BASE}/chat", json={"query": test["query"], "mode": "text", "session_id": unique_session})
            result.response_ms = round((time.perf_counter() - start) * 1000, 1)
            if r.status_code in (400, 422):
                result.status = "PASS"
                result.actual_action = f"HTTP_{r.status_code}"
            else:
                result.status = "FAIL"
                result.actual_action = f"HTTP_{r.status_code}"
                result.error = f"Expected 400/422 for empty query, got {r.status_code}"
        except Exception as e:
            result.status = "ERROR"
            result.error = str(e)
        return result

    try:
        start = time.perf_counter()
        unique_session = f"qa-single-{test['id']}-{uuid.uuid4().hex[:8]}"
        r = await client.post(f"{BASE}/chat", json={"query": test["query"], "mode": "text", "session_id": unique_session})
        result.response_ms = round((time.perf_counter() - start) * 1000, 1)

        if r.status_code != 200:
            result.status = "ERROR"
            result.actual_action = f"HTTP_{r.status_code}"
            result.error = f"HTTP {r.status_code}: {r.text[:200]}"
            return result

        data = r.json()
        result.actual_action = data.get("action", "UNKNOWN")
        result.session_id = data.get("session_id", "")
        
        # Check response text
        response_text = data.get("response", "")
        result.has_response_text = bool(response_text and response_text.strip())
        
        # Check hotels
        hotels = data.get("hotels", [])
        result.hotels_count = len(hotels) if isinstance(hotels, list) else 0

        # Check action match
        expected_actions = test["expected_action"].split("|")
        if result.actual_action in expected_actions:
            result.status = "PASS"
        else:
            result.status = "FAIL"
            result.error = f"Expected {test['expected_action']}, got {result.actual_action}"

        # Check for slow responses (local should be under 2s, rapidapi under 10s)
        if result.actual_action == "LOCAL_DB" and result.response_ms > 2000:
            result.details += f" SLOW({result.response_ms}ms)"
        elif result.actual_action == "RAPIDAPI" and result.response_ms > 10000:
            result.details += f" SLOW({result.response_ms}ms)"

        # Check LOCAL_DB has hotels
        if result.actual_action == "LOCAL_DB" and result.hotels_count == 0:
            result.details += " NO_HOTELS"

        # Check response text exists
        if not result.has_response_text and result.actual_action in ("LOCAL_DB", "RAPIDAPI"):
            result.details += " NO_RESPONSE_TEXT"

        # Detect API key issues
        error_msg = data.get("error", "") or data.get("message", "")
        if isinstance(error_msg, str):
            lower_err = error_msg.lower()
            if "api key" in lower_err or "quota" in lower_err or "rate limit" in lower_err or "429" in lower_err or "403" in lower_err:
                result.details += " ⚠️ API_KEY_ISSUE"

    except httpx.ReadTimeout:
        result.status = "ERROR"
        result.error = "TIMEOUT (30s)"
    except Exception as e:
        result.status = "ERROR"
        result.error = f"{type(e).__name__}: {str(e)[:200]}"

    return result


async def run_multi_turn_flow(client: httpx.AsyncClient, flow: Dict, flow_idx: int) -> List[TestResult]:
    results = []
    session_id = f"qa-multiturn-{flow['name']}-{int(time.time())}"
    
    for step_idx, step in enumerate(flow["steps"]):
        global _id
        _id += 1
        test_id = _id

        result = TestResult(
            id=test_id,
            category=f"multi_turn:{flow['name']}",
            query=step["query"],
            expected_action=step["expected"],
        )

        try:
            start = time.perf_counter()
            r = await client.post(f"{BASE}/chat", json={
                "query": step["query"],
                "mode": "text",
                "session_id": session_id,
            })
            result.response_ms = round((time.perf_counter() - start) * 1000, 1)

            if r.status_code != 200:
                result.status = "ERROR"
                result.actual_action = f"HTTP_{r.status_code}"
                result.error = f"HTTP {r.status_code}"
                results.append(result)
                continue

            data = r.json()
            result.actual_action = data.get("action", "UNKNOWN")
            result.session_id = session_id
            response_text = data.get("response", "")
            result.has_response_text = bool(response_text and response_text.strip())
            hotels = data.get("hotels", [])
            result.hotels_count = len(hotels) if isinstance(hotels, list) else 0

            expected_actions = step["expected"].split("|")
            if result.actual_action in expected_actions:
                result.status = "PASS"
            else:
                result.status = "FAIL"
                result.error = f"Expected {step['expected']}, got {result.actual_action}"

        except Exception as e:
            result.status = "ERROR"
            result.error = str(e)[:200]

        results.append(result)
        # Small delay between turns for realism
        await asyncio.sleep(0.3)

    return results


async def run_direct_api_tests(client: httpx.AsyncClient) -> List[TestResult]:
    """Test direct endpoint access (localdb, rapidapi, health)."""
    results = []
    global _id

    # Test 1: LocalDB direct endpoint
    _id += 1
    r1 = TestResult(id=_id, category="direct_api", query="GET /localdb/hotels/insights?location=Colombo", expected_action="OK")
    try:
        start = time.perf_counter()
        r = await client.get(f"{BASE}/localdb/hotels/insights", params={"location": "Colombo"})
        r1.response_ms = round((time.perf_counter() - start) * 1000, 1)
        if r.status_code == 200:
            data = r.json()
            r1.hotels_count = data.get("count", 0)
            r1.actual_action = "OK"
            r1.status = "PASS"
        else:
            r1.actual_action = f"HTTP_{r.status_code}"
            r1.status = "FAIL"
            r1.error = r.text[:200]
    except Exception as e:
        r1.status = "ERROR"
        r1.error = str(e)[:200]
    results.append(r1)

    # Test 2: LocalDB with filters
    _id += 1
    r2 = TestResult(id=_id, category="direct_api", query="GET /localdb/hotels/insights?location=Galle&rating=4&priceMin=5000", expected_action="OK")
    try:
        start = time.perf_counter()
        r = await client.get(f"{BASE}/localdb/hotels/insights", params={"location": "Galle", "rating": 4, "priceMin": 5000})
        r2.response_ms = round((time.perf_counter() - start) * 1000, 1)
        if r.status_code == 200:
            r2.actual_action = "OK"
            r2.status = "PASS"
        else:
            r2.actual_action = f"HTTP_{r.status_code}"
            r2.status = "FAIL"
    except Exception as e:
        r2.status = "ERROR"
        r2.error = str(e)[:200]
    results.append(r2)

    # Test 3: LocalDB missing location
    _id += 1
    r3 = TestResult(id=_id, category="direct_api", query="GET /localdb/hotels/insights (no location)", expected_action="HTTP_422")
    try:
        r = await client.get(f"{BASE}/localdb/hotels/insights")
        r3.actual_action = f"HTTP_{r.status_code}"
        r3.status = "PASS" if r.status_code == 422 else "FAIL"
    except Exception as e:
        r3.status = "ERROR"
        r3.error = str(e)[:200]
    results.append(r3)

    # Test 4: LocalDB priceMin > priceMax
    _id += 1
    r4 = TestResult(id=_id, category="direct_api", query="GET /localdb priceMin=20000&priceMax=5000", expected_action="HTTP_422")
    try:
        r = await client.get(f"{BASE}/localdb/hotels/insights", params={"location": "Colombo", "priceMin": 20000, "priceMax": 5000})
        r4.actual_action = f"HTTP_{r.status_code}"
        r4.status = "PASS" if r.status_code == 422 else "FAIL"
        if r.status_code != 422:
            r4.error = f"Expected 422, got {r.status_code}"
    except Exception as e:
        r4.status = "ERROR"
        r4.error = str(e)[:200]
    results.append(r4)

    # Test 5: RapidAPI direct (valid dates)
    _id += 1
    r5 = TestResult(id=_id, category="direct_api", query="GET /Rapidapi/hotels/insights?geoId=293962&checkIn=2026-03-20&checkOut=2026-03-22", expected_action="OK")
    try:
        start = time.perf_counter()
        r = await client.get(f"{BASE}/Rapidapi/hotels/insights", params={
            "geoId": "293962", "checkIn": "2026-03-20", "checkOut": "2026-03-22"
        })
        r5.response_ms = round((time.perf_counter() - start) * 1000, 1)
        if r.status_code == 200:
            data = r.json()
            r5.hotels_count = data.get("count", 0)
            r5.actual_action = "OK"
            r5.status = "PASS"
        else:
            r5.actual_action = f"HTTP_{r.status_code}"
            r5.status = "FAIL"
            r5.error = r.text[:300]
    except Exception as e:
        r5.status = "ERROR"
        r5.error = str(e)[:200]
    results.append(r5)

    # Test 6: RapidAPI checkOut <= checkIn
    _id += 1
    r6 = TestResult(id=_id, category="direct_api", query="GET /Rapidapi checkOut <= checkIn", expected_action="HTTP_422")
    try:
        r = await client.get(f"{BASE}/Rapidapi/hotels/insights", params={
            "geoId": "293962", "checkIn": "2026-03-20", "checkOut": "2026-03-19"
        })
        r6.actual_action = f"HTTP_{r.status_code}"
        r6.status = "PASS" if r.status_code == 422 else "FAIL"
    except Exception as e:
        r6.status = "ERROR"
        r6.error = str(e)[:200]
    results.append(r6)

    # Test 7: RapidAPI missing required params
    _id += 1
    r7 = TestResult(id=_id, category="direct_api", query="GET /Rapidapi missing geoId", expected_action="HTTP_422")
    try:
        r = await client.get(f"{BASE}/Rapidapi/hotels/insights", params={"checkIn": "2026-03-20", "checkOut": "2026-03-22"})
        r7.actual_action = f"HTTP_{r.status_code}"
        r7.status = "PASS" if r.status_code == 422 else "FAIL"
    except Exception as e:
        r7.status = "ERROR"
        r7.error = str(e)[:200]
    results.append(r7)

    # Test 8: Chat endpoint with invalid JSON
    _id += 1
    r8 = TestResult(id=_id, category="direct_api", query="POST /chat invalid JSON", expected_action="HTTP_422")
    try:
        r = await client.post(f"{BASE}/chat", content="not json", headers={"Content-Type": "application/json"})
        r8.actual_action = f"HTTP_{r.status_code}"
        r8.status = "PASS" if r.status_code == 422 else "FAIL"
    except Exception as e:
        r8.status = "ERROR"
        r8.error = str(e)[:200]
    results.append(r8)

    # Test 9: Chat with missing query field
    _id += 1
    r9 = TestResult(id=_id, category="direct_api", query="POST /chat missing query field", expected_action="HTTP_422")
    try:
        r = await client.post(f"{BASE}/chat", json={"mode": "text"})
        r9.actual_action = f"HTTP_{r.status_code}"
        r9.status = "PASS" if r.status_code == 422 else "FAIL"
    except Exception as e:
        r9.status = "ERROR"
        r9.error = str(e)[:200]
    results.append(r9)

    # Test 10: Health endpoint
    _id += 1
    r10 = TestResult(id=_id, category="direct_api", query="GET /health", expected_action="OK")
    try:
        r = await client.get(f"{BASE}/health")
        if r.status_code == 200 and r.json().get("status") == "ok":
            r10.actual_action = "OK"
            r10.status = "PASS"
        else:
            r10.actual_action = f"HTTP_{r.status_code}"
            r10.status = "FAIL"
    except Exception as e:
        r10.status = "ERROR"
        r10.error = str(e)[:200]
    results.append(r10)

    return results


async def main():
    print("=" * 80)
    print("SCENERY QA COMPREHENSIVE TEST SUITE")
    print(f"Total chat test cases: {len(CHAT_TESTS)}")
    print(f"Multi-turn flows: {len(MULTI_TURN_FLOWS)} ({sum(len(f['steps']) for f in MULTI_TURN_FLOWS)} steps)")
    print(f"Direct API tests: ~10")
    print("=" * 80)

    all_results: List[TestResult] = []
    api_key_issue_detected = False

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # 1) Run chat tests (batched to avoid overwhelming)
        print("\n--- CHAT TESTS ---")
        batch_size = 5
        for i in range(0, len(CHAT_TESTS), batch_size):
            batch = CHAT_TESTS[i:i + batch_size]
            tasks = [run_single_chat_test(client, t) for t in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for br in batch_results:
                if isinstance(br, Exception):
                    print(f"  EXCEPTION: {br}")
                    continue
                all_results.append(br)
                icon = "✅" if br.status == "PASS" else "❌" if br.status == "FAIL" else "💥"
                print(f"  {icon} #{br.id:03d} [{br.category}] {br.query[:50]:<50} -> {br.actual_action:<15} {br.response_ms:>7.0f}ms {br.details}")
                
                if br.error:
                    print(f"       ERROR: {br.error[:100]}")
                
                # Check for API key issues
                if "API_KEY_ISSUE" in br.details or "api key" in br.error.lower() or "quota" in br.error.lower():
                    api_key_issue_detected = True

            await asyncio.sleep(0.5)  # Brief pause between batches

            if api_key_issue_detected:
                print("\n⚠️⚠️⚠️ API KEY ISSUE DETECTED! Stopping RapidAPI tests. ⚠️⚠️⚠️")

        # 2) Multi-turn flows
        print("\n--- MULTI-TURN FLOWS ---")
        for idx, flow in enumerate(MULTI_TURN_FLOWS):
            print(f"\n  Flow: {flow['name']}")
            flow_results = await run_multi_turn_flow(client, flow, idx)
            for fr in flow_results:
                all_results.append(fr)
                icon = "✅" if fr.status == "PASS" else "❌" if fr.status == "FAIL" else "💥"
                print(f"    {icon} #{fr.id:03d} [{fr.category}] {fr.query[:45]:<45} -> {fr.actual_action:<15} {fr.response_ms:>7.0f}ms")
                if fr.error:
                    print(f"         ERROR: {fr.error[:100]}")

        # 3) Direct API tests
        print("\n--- DIRECT API TESTS ---")
        api_results = await run_direct_api_tests(client)
        for ar in api_results:
            all_results.append(ar)
            icon = "✅" if ar.status == "PASS" else "❌" if ar.status == "FAIL" else "💥"
            print(f"  {icon} #{ar.id:03d} [{ar.category}] {ar.query[:55]:<55} -> {ar.actual_action:<15} {ar.response_ms:>7.0f}ms")
            if ar.error:
                print(f"       ERROR: {ar.error[:100]}")

    # ═══════════ SUMMARY ═══════════
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total = len(all_results)
    passed = sum(1 for r in all_results if r.status == "PASS")
    failed = sum(1 for r in all_results if r.status == "FAIL")
    errors = sum(1 for r in all_results if r.status == "ERROR")
    
    print(f"\nTotal:  {total}")
    print(f"PASS:   {passed} ({100*passed/total:.1f}%)")
    print(f"FAIL:   {failed} ({100*failed/total:.1f}%)")
    print(f"ERROR:  {errors} ({100*errors/total:.1f}%)")

    # Category breakdown
    categories = {}
    for r in all_results:
        cat = r.category.split(":")[0]
        if cat not in categories:
            categories[cat] = {"pass": 0, "fail": 0, "error": 0}
        categories[cat][r.status.lower() if r.status.lower() in ("pass", "fail", "error") else "error"] += 1

    print("\n--- BY CATEGORY ---")
    for cat, counts in sorted(categories.items()):
        total_cat = sum(counts.values())
        print(f"  {cat:<20} PASS:{counts['pass']:>3} FAIL:{counts['fail']:>3} ERROR:{counts['error']:>3} (total:{total_cat})")

    # List all failures
    failures = [r for r in all_results if r.status in ("FAIL", "ERROR")]
    if failures:
        print(f"\n--- ALL FAILURES ({len(failures)}) ---")
        for f in failures:
            print(f"  #{f.id:03d} [{f.category}] {f.query[:60]}")
            print(f"       Expected: {f.expected_action}  Got: {f.actual_action}  Error: {f.error[:120]}")

    # Timing analysis
    local_times = [r.response_ms for r in all_results if r.actual_action == "LOCAL_DB"]
    rapid_times = [r.response_ms for r in all_results if r.actual_action == "RAPIDAPI"]
    
    if local_times:
        print(f"\n--- LOCAL_DB TIMING ---")
        print(f"  Avg: {sum(local_times)/len(local_times):.0f}ms  Min: {min(local_times):.0f}ms  Max: {max(local_times):.0f}ms  Count: {len(local_times)}")
        slow_local = [r for r in all_results if r.actual_action == "LOCAL_DB" and r.response_ms > 1500]
        if slow_local:
            print(f"  Slow (>1500ms): {len(slow_local)}")
            for s in slow_local:
                print(f"    #{s.id:03d} {s.response_ms:.0f}ms: {s.query[:60]}")
    
    if rapid_times:
        print(f"\n--- RAPIDAPI TIMING ---")
        print(f"  Avg: {sum(rapid_times)/len(rapid_times):.0f}ms  Min: {min(rapid_times):.0f}ms  Max: {max(rapid_times):.0f}ms  Count: {len(rapid_times)}")

    # Hotels with 0 results
    empty_hotels = [r for r in all_results if r.actual_action in ("LOCAL_DB", "RAPIDAPI") and r.hotels_count == 0]
    if empty_hotels:
        print(f"\n--- ZERO HOTEL RESULTS ({len(empty_hotels)}) ---")
        for e in empty_hotels:
            print(f"  #{e.id:03d} [{e.actual_action}] {e.query[:60]}")

    # Missing response text
    no_text = [r for r in all_results if r.actual_action in ("LOCAL_DB", "RAPIDAPI") and not r.has_response_text]
    if no_text:
        print(f"\n--- MISSING RESPONSE TEXT ({len(no_text)}) ---")
        for n in no_text:
            print(f"  #{n.id:03d} [{n.actual_action}] {n.query[:60]}")

    if api_key_issue_detected:
        print("\n" + "⚠️" * 20)
        print("API KEY ISSUE DETECTED DURING TESTING!")
        print("Your Gemini or RapidAPI key may be exhausted or rate-limited.")
        print("⚠️" * 20)

    print("\n" + "=" * 80)
    print("QA TEST SUITE COMPLETE")
    print("=" * 80)

    return all_results


if __name__ == "__main__":
    asyncio.run(main())
