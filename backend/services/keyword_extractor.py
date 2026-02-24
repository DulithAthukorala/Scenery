"""
This module contains logic to extract information from user queries. 
    - location
    - check-in/check-out dates
    - number of people/rooms 
    - budget.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional, Tuple

import spacy
from rapidfuzz import fuzz
from dateparser.search import search_dates


@dataclass
class Slots:
    location: Optional[str] = None
    check_in: Optional[date] = None
    check_out: Optional[date] = None
    adults: Optional[int] = None
    rooms: Optional[int] = None
    price_min: Optional[int] = None
    price_max: Optional[int] = None


# Start with a list; later load from DB + cache it.
SUPPORTED_LOCATIONS = [
    "Colombo", "Galle", "Kandy", "Ella", "Mirissa", "Unawatuna", "Hikkaduwa",
    "Negombo", "Nuwara Eliya", "Sigiriya", "Bentota", "Trincomalee", "Arugam Bay",
    "Tangalle", "Weligama", "Dambulla", "Anuradhapura", "Jaffna", "Pasikudah", "Nilaveli"
]

# remove currency words like "lkr", "rs", "rupees" in query
_CURRENCY_WORDS_RE = re.compile(r"(lkr|rs\.?|rup|rupees)", re.IGNORECASE)

# match money like "25000", "25,000", "12.5k", "25k" in query
_MONEY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(k)?", re.IGNORECASE)

# budget patterns
_BETWEEN_RE = re.compile(r"(between|from)\s+([^\s]+)\s+(and|to)\s+([^\s]+)", re.IGNORECASE)
_UNDER_RE   = re.compile(r"(under|below|less than|up to)\s+([^\s]+)", re.IGNORECASE)
_ABOVE_RE   = re.compile(r"(above|more than|over|at least)\s+([^\s]+)", re.IGNORECASE)

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")  # english core web trained small model
    return _nlp


def _normalize_money_to_int(text: str) -> Optional[int]:
    t = text.strip()
    t = t.replace(",", "")                      # remove commas
    t = _CURRENCY_WORDS_RE.sub("", t).strip()   # remove currency words

    m = _MONEY_RE.search(t)
    if not m:
        return None

    val = float(m.group(1))
    if m.group(2) and m.group(2).lower() == "k":   # if "k" present
        val *= 1000
    return int(val)


def _extract_budget(query: str) -> Tuple[Optional[int], Optional[int]]:
    q = query.lower()

    m = _BETWEEN_RE.search(q)
    if m:
        a = _normalize_money_to_int(m.group(2))
        b = _normalize_money_to_int(m.group(4))
        if a is not None and b is not None:
            return min(a, b), max(a, b)

    m = _UNDER_RE.search(q)
    if m:
        mx = _normalize_money_to_int(m.group(2))
        return None, mx

    m = _ABOVE_RE.search(q)
    if m:
        mn = _normalize_money_to_int(m.group(2))
        return mn, None

    return None, None


def _extract_people_rooms(query: str) -> Tuple[Optional[int], Optional[int]]:
    q = query.lower()
    adults = None
    rooms = None

    m = re.search(r"(\d+)\s*(adults|adult|people|persons|guests)", q)
    if m:
        adults = int(m.group(1))

    m = re.search(r"(\d+)\s*(rooms|room)", q)
    if m:
        rooms = int(m.group(1))

    return adults, rooms


def _extract_dates(query: str) -> Tuple[Optional[date], Optional[date]]:
    found = search_dates(query, languages=["en"])
    if not found:
        return None, None

    ds = []
    for _, dt in found:
        d = dt.date()
        if not ds or d != ds[-1]:
            ds.append(d)
        if len(ds) == 2:
            break

    if len(ds) == 1:
        return ds[0], None
    return ds[0], ds[1]


def _extract_location(query: str) -> Optional[str]:
    # 1) Try spaCy GPE/LOC first
    doc = _get_nlp()(query)
    candidates = [ent.text for ent in doc.ents if ent.label_ in ("GPE", "LOC")]
    if candidates:
        # prefer longest
        return sorted(candidates, key=len, reverse=True)[0]

    # 2) Fallback fuzzy against supported locations
    t = query.lower()
    best_loc = None
    best_score = 0
    for loc in SUPPORTED_LOCATIONS:
        score = fuzz.partial_ratio(t, loc.lower())
        if score > best_score:
            best_loc, best_score = loc, score
    return best_loc if best_score >= 85 else None


def extract_slots(user_query: str) -> Slots:
    location = _extract_location(user_query)
    check_in, check_out = _extract_dates(user_query)
    adults, rooms = _extract_people_rooms(user_query)
    price_min, price_max = _extract_budget(user_query)

    return Slots(
        location=location,
        check_in=check_in,
        check_out=check_out,
        adults=adults,
        rooms=rooms,
        price_min=price_min,
        price_max=price_max,
    )
