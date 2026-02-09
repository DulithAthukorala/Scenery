"""
TripAdvisor endpoints. This includes hotel search and other related functionality.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from backend.services.tripadvisor_rapidapi import search_hotels, RapidAPIError

router = APIRouter(prefix="/tripadvisor", tags=["tripadvisor"])


@router.get("/hotels/search")
async def hotels_search(
    geoId: str = Query(..., description="Tripadvisor geoId from SearchLocation (Hotels collection)"),
    checkIn: date = Query(
        ...,
        description="Check-in date",
        openapi_extra={"format": "date", "example": "2026-02-14"},
    ),
    checkOut: date = Query(
        ...,
        description="Check-out date",
        openapi_extra={"format": "date", "example": "2026-02-15"},
    ),
    pageNumber: int = Query(1, ge=1, description="Page number (default 1)"),
    sort: str = Query("BEST_VALUE", description="Sort option (e.g., BEST_VALUE)"),
    adults: int = Query(2, ge=1, le=20, description="Number of adults"),
    rooms: int = Query(1, ge=1, le=10, description="Number of rooms"),
    currencyCode: str = Query("LKR", min_length=3, max_length=3, description="Currency code (e.g., LKR)"),
    rating: Optional[int] = Query(None, ge=0, le=5, description="Minimum rating filter"),
    priceMin: Optional[int] = Query(None, ge=0, description="Minimum price filter"),
    priceMax: Optional[int] = Query(None, ge=0, description="Maximum price filter"),

    # Arrays: Swagger sends these as repeated keys:
    # childrenAges=5&childrenAges=9
    childrenAges: Optional[List[int]] = Query(None, description="Children ages (repeat param)"),
    amenity: Optional[List[str]] = Query(None, description="Amenities (repeat param)"),
    neighborhood: Optional[List[str]] = Query(None, description="Neighborhood filters (repeat param)"),
    deals: Optional[List[str]] = Query(None, description="Deals (repeat param)"),
    type: Optional[List[str]] = Query(None, description="Hotel type filters (repeat param)"),
    class_: Optional[List[str]] = Query(None, alias="class", description="Hotel class filters (repeat param)"),
    style: Optional[List[str]] = Query(None, description="Style filters (repeat param)"),
    brand: Optional[List[str]] = Query(None, description="Brand filters (repeat param)"),
):
    # Sanity rule: checkout must be after checkin
    if checkOut <= checkIn:
        raise HTTPException(status_code=422, detail="checkOut must be after checkIn")

    try:
        return await search_hotels(
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
            type_=type,
            class_=class_,
            style=style,
            brand=brand,
        )

    except RapidAPIError as e:
        # Preserve the upstream status code + payload for debugging
        raise HTTPException(status_code=e.status_code, detail={"message": str(e), "upstream": e.payload})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Internal server error", "error": repr(e)})
