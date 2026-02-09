from __future__ import annotations

import httpx
from datetime import date
from typing import Optional, List, Tuple, Any, Dict

from backend.config import RAPIDAPI_KEY, RAPIDAPI_HOST

BASE_URL = "https://tripadvisor16.p.rapidapi.com"


class RapidAPIError(RuntimeError):
    """Raised when RapidAPI returns a non-2xx response."""

    def __init__(self, status_code: int, message: str, payload: Any = None):
        super().__init__(message)
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
        "Accept": "application/json",
    }


def _iso(d: date) -> str:
    # RapidAPI docs + your curl show ISO YYYY-MM-DD
    return d.isoformat()


def _build_params(
    geoId: str,
    checkIn: date,
    checkOut: date,
    pageNumber: int,
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
    brand: Optional[List[str]],
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

    def add_list(key: str, values: Optional[List[str]]):
        if values:
            for v in values:
                params.append((key, v))

    add_list("amenity", amenity)
    add_list("neighborhood", neighborhood)
    add_list("deals", deals)
    add_list("type", type_)
    add_list("class", class_)
    add_list("style", style)
    add_list("brand", brand)

    return params


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
      GET https://tripadvisor16.p.rapidapi.com/api/v1/hotels/searchHotels

    Dates are sent as YYYY-MM-DD (ISO), per your working curl.
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

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=_headers(), params=params)

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

    return r.json()
