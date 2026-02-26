"""
Service for interacting with TripAdvisor's RapidAPI endpoints. This includes hotel search and other related functionality.
"""
from __future__ import annotations

import httpx  # Async HTTP client library(for fast API calls to RapidAPI)
import time  # caching timestamps
from datetime import date
from typing import Optional, List, Tuple, Any, Dict, Union

from backend.config import RAPIDAPI_KEY, RAPIDAPI_HOST

BASE_URL = "https://tripadvisor16.p.rapidapi.com"


# ----------------------------
# Simple in-memory cache (Phase 1)
# ----------------------------
# NOTE: This cache is per-process (if you run multiple workers, each has its own cache)
# TTL controls how long we reuse RapidAPI results for identical params.
_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 15 * 60  # 15 minutes


def _cache_key(url: str, params: List[Tuple[str, str]]) -> str:
    """
    Build a stable cache key from url + sorted params.
    Sorting makes the key independent of param order.
    """
    normalized = "&".join(f"{k}={v}" for k, v in sorted(params))
    return f"{url}?{normalized}"


def _get_cached(key: str) -> Optional[Dict[str, Any]]:
    entry = _CACHE.get(key)
    if not entry:
        return None

    ts, data = entry
    if time.time() - ts > CACHE_TTL_SECONDS:
        # expired
        del _CACHE[key]
        return None

    return data


def _set_cache(key: str, data: Dict[str, Any]) -> None:
    _CACHE[key] = (time.time(), data)


class RapidAPIError(RuntimeError):
    """Raised when RapidAPI returns a non-2xx(unsuccessful) response."""

    def __init__(self, status_code: int, message: str, payload: Any = None):
        super().__init__(message)  # RuntimeError.__init__(message)
        self.status_code = status_code
        self.payload = payload


def _headers() -> Dict[str, str]:
    if not RAPIDAPI_KEY or not RAPIDAPI_HOST:
        raise RapidAPIError(
            status_code=500,
            message="RapidAPI credentials missing (RAPIDAPI_KEY / RAPIDAPI_HOST).",
        )
    return {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Accept": "application/json",  # Ensure we get JSON responses
    }


def _iso(d) -> str:
    # RapidAPI docs + your curl show ISO YYYY-MM-DD
    # Handle both date objects and ISO strings
    if isinstance(d, str):
        return d
    return d.isoformat()


def _build_params(
    geoId: str,
    checkIn: date,
    checkOut: date,
    pageNumber: int,  # Not to have abc, later converted to str
    sort: str,
    adults: int,
    rooms: int,
    currencyCode: str,
    rating: Optional[int],
    priceMin: Optional[int],
    priceMax: Optional[int],
    childrenAges: Optional[List[int]],
    amenity: Optional[List[str]],
    neighborhood: Optional[List[str]],
    deals: Optional[List[str]],
    type_: Optional[List[str]], 
    class_: Optional[List[str]],
    style: Optional[List[str]],
    brand: Optional[List[str]], # hotel chains like Hilton, Marriott
) -> List[Tuple[str, str]]:
    """
    Build params as list-of-tuples so arrays are sent as repeated query keys:
      amenity=pool&amenity=wifi
      childrenAges=5&childrenAges=9
    This matches how many RapidAPI "Array" fields are expected.
    """
    params: List[Tuple[str, str]] = [
        ("geoId", geoId),
        ("checkIn", _iso(checkIn)),
        ("checkOut", _iso(checkOut)),
        ("pageNumber", str(pageNumber)),
        ("sort", sort),
        ("adults", str(adults)),
        ("rooms", str(rooms)),
        ("currencyCode", currencyCode),
    ]

    if rating is not None:
        params.append(("rating", str(rating)))
    if priceMin is not None:
        params.append(("priceMin", str(priceMin)))
    if priceMax is not None:
        params.append(("priceMax", str(priceMax)))

    if childrenAges:
        for age in childrenAges:
            params.append(("childrenAges", str(age)))

    def add_csv(key: str, values: Optional[Union[list[str], str]]):
        """
        Accepts:
        - ["pool", "wifi"]
        - "pool,wifi"

        Normalizes → "pool,wifi"
        """
        if not values:
            return

        if isinstance(values, str):
            items = [v.strip() for v in values.split(",") if v.strip()]
        else:
            items = [v.strip() for v in values if v.strip()]

        if items:
            params.append((key, ",".join(items)))

    add_csv("amenity", amenity)
    add_csv("neighborhood", neighborhood)
    add_csv("deals", deals)
    add_csv("type", type_)
    add_csv("class", class_)
    add_csv("style", style)
    add_csv("brand", brand)

    return params


# async def bcz await is being used inside
# * -> search_hotels(geoID=...,) not searchHotels(...,)
async def search_hotels(
    *,
    geoId: str,
    checkIn: date,
    checkOut: date,
    pageNumber: int = 1,
    sort: str = "BEST_VALUE",
    adults: int = 2,
    rooms: int = 1,
    currencyCode: str = "LKR",
    rating: Optional[int] = None,
    priceMin: Optional[int] = None,
    priceMax: Optional[int] = None,
    childrenAges: Optional[List[int]] = None,
    amenity: Optional[List[str]] = None,
    neighborhood: Optional[List[str]] = None,
    deals: Optional[List[str]] = None,
    type_: Optional[List[str]] = None,
    class_: Optional[List[str]] = None,
    style: Optional[List[str]] = None,
    brand: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Calls:
      GET https://tripadvisor16.p.rapidapi.com/api/v1/hotels/searchHotels.
    """
    url = f"{BASE_URL}/api/v1/hotels/searchHotels"
    params = _build_params(
        geoId=geoId,
        checkIn=checkIn,
        checkOut=checkOut,
        pageNumber=pageNumber,
        sort=sort,
        adults=adults,
        rooms=rooms,
        currencyCode=currencyCode,
        rating=rating,
        priceMin=priceMin,
        priceMax=priceMax,
        childrenAges=childrenAges,
        amenity=amenity,
        neighborhood=neighborhood,
        deals=deals,
        type_=type_,
        class_=class_,
        style=style,
        brand=brand,
    )

    # ----------------------------
    # Cache lookup (same params → instant)
    # ----------------------------
    cache_key = _cache_key(url, params)
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    # Debug: Log the request
    print(f"DEBUG: RapidAPI Request URL: {url}")
    print(f"DEBUG: RapidAPI Params: {params}")

    async with httpx.AsyncClient(timeout=30) as client:  # create async client with 30s timeout & close
        r = await client.get(url, headers=_headers(), params=params)

    print(f"DEBUG: RapidAPI Response Status: {r.status_code}")
    print(f"DEBUG: RapidAPI Response: {r.text[:500]}")  # First 500 chars

    if r.status_code >= 400:
        # Try JSON; fallback to text
        try:
            payload = r.json()
        except Exception:
            payload = {"raw": r.text}

        raise RapidAPIError(
            status_code=r.status_code,
            message=f"RapidAPI error {r.status_code} calling searchHotels",
            payload=payload,
        )

    data = r.json()

    # ----------------------------
    # Cache set
    # ----------------------------
    _set_cache(cache_key, data)

    return data
