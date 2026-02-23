"""
This service is turns user location strings into geoIds for hotel queries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Dict


@dataclass(frozen=True)
class GeoResolveResult:
    geo_id: Optional[int]
    normalized_query: str
    strategy: str  # "direct_id" | "map" | "unknown"


# Can be expanded in the future with more cities 
CITY_GEOIDS: Dict[str, int] = {
    "colombo": 293962,
    "kandy": 304138,
    "galle": 189825,
    "ella": 616035,
    "nuwara eliya": 608524,
    "sigiriya": 304141,
    "mirissa": 1407334,
    "negombo": 297897,
    "trincomalee": 424963,
    "arugam bay": 3348959,
    "jaffna": 304135,
    "hambantota": 424962,
    "anuradhapura": 304132,
    "polonnaruwa": 304139,
    "chilaw": 447558,
}


def _normalize(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def resolve_geo_id(location: str) -> GeoResolveResult:
    """
    Convert user location string -> geoId for RapidAPI.
    """
    raw = (location or "").strip()
    if not raw:
        return GeoResolveResult(None, "", "unknown")

    # If already numeric
    if raw.isdigit():
        return GeoResolveResult(int(raw), raw, "direct_id")

    norm = _normalize(raw)

    # Exact match
    if norm in CITY_GEOIDS:
        return GeoResolveResult(CITY_GEOIDS[norm], norm, "map")

    # Try last words (e.g. "hotels in colombo")
    for city in CITY_GEOIDS:
        if city in norm:
            return GeoResolveResult(CITY_GEOIDS[city], city, "map")

    return GeoResolveResult(None, norm, "unknown")