from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional


# Tripadvisor(RapidAPI) geoIds
CITY_GEOIDS: Dict[str, int] = {
    "Colombo": 293962,
    "Kandy": 304138,
    "Galle": 297896,
    "Ella": 616035,
    "Nuwara Eliya": 608524,
    "Sigiriya": 304141,
    "Mirissa": 1407334,
    "Negombo": 297897,
    "Trincomalee": 424963,
    "Arugam Bay": 3348959,
    "Jaffna": 304135,
    "Hambantota": 1027209,
    "Anuradhapura": 304132,
    "Polonnaruwa": 304139,
    "Chilaw": 447558,
}


@dataclass(frozen=True)
class GeoResolveResult:
    geo_id: Optional[int]
    matched_city: str
    reason: str  # "direct_id" | "map" | "unknown"


_WORDS_ONLY = re.compile(r"[^a-zA-Z\s]+") # Keep only letters and spaces. Remove everything else


def _normalize(text: str) -> str:
    t = (text or "").strip()
    t = _WORDS_ONLY.sub(" ", t)
    t = " ".join(t.split())
    return t.lower()


def convert_geo_id(location: str) -> GeoResolveResult:
    """
    Convert user location string -> geoId.
    """
    raw = (location or "").strip()
    if not raw:
        return GeoResolveResult(None, "", "unknown")

    # If already numeric
    if raw.isdigit():
        return GeoResolveResult(int(raw), raw, "direct_id")

    norm = _normalize(raw)

    # exact match against keys
    for city, gid in CITY_GEOIDS.items():
        if _normalize(city) == norm:
            return GeoResolveResult(gid, city, "map")

    # city appears inside phrase (not used but added for robustness)
    for city, gid in CITY_GEOIDS.items():
        if _normalize(city) in norm:
            return GeoResolveResult(gid, city, "map")

    return GeoResolveResult(None, raw, "Could not find a matching geoid for location")


# ---------------------------------------------------------------------------
# Fuzzy city matching (used by decision engine for typo tolerance)
# ---------------------------------------------------------------------------


def fuzzy_match_city(text: str, threshold: int = 72) -> Optional[str]:
    """
    Return the best-matching city name from CITY_GEOIDS if the similarity
    score exceeds *threshold*, else ``None``.

    Uses Levenshtein-based token_set_ratio for robustness against word-order
    and partial matches (e.g. "nuwara" → "Nuwara Eliya").
    """
    from rapidfuzz import fuzz as _fuzz  # lazy import to keep startup fast

    query = _normalize(text)
    if not query:
        return None

    best_score = 0
    best_city: Optional[str] = None

    for city in CITY_GEOIDS:
        score = _fuzz.token_set_ratio(query, _normalize(city))
        if score > best_score:
            best_score = score
            best_city = city

    if best_score >= threshold and best_city is not None:
        return best_city
    return None