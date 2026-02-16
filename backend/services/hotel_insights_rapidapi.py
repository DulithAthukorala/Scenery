from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.services.hotel_raw_json import search_hotels
from backend.services.hotel_normalize import normalize_tripadvisor_hotels


async def get_hotel_insights(
    *,
    geoId: str,
    checkIn,
    checkOut,
    pageNumber: int = 1,
    sort: str = "BEST_VALUE",
    adults: int = 2,
    rooms: int = 1,
    currencyCode: str = "LKR",
    rating: Optional[int] = None,
    priceMin: Optional[int] = None,
    priceMax: Optional[int] = None,
    amenity: Optional[List[str]] = None,
    neighborhood: Optional[List[str]] = None,
    deals: Optional[List[str]] = None,
    type_: Optional[List[str]] = None,
    class_: Optional[List[str]] = None,
    style: Optional[List[str]] = None,
    brand: Optional[List[str]] = None,
    user_request: str = "Find the best value hotel for me.",
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Fetch hotels from RapidAPI and return normalized results.
    user_request is accepted but not used for ranking.
    """

    # 1) Fetch live data
    raw = await search_hotels(
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
        amenity=amenity,
        neighborhood=neighborhood,
        deals=deals,
        type_=type_,
        class_=class_,
        style=style,
        brand=brand,
    )

    # 2) Normalize
    hotels = normalize_tripadvisor_hotels(raw, limit=limit)

    return {
        "source": "rapidapi",
        "user_request": user_request,   # kept for API compatibility
        "count": len(hotels),
        "results": hotels,
        "meta": {
            "sort": sort,
            "currency": currencyCode,
        },
    }
