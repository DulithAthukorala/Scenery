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
    geoId: str = Query(..., description="Tripadvisor geoId from SearchLocation (city/country of travel)"),
    checkIn: date = Query(
        ...,
        description="Check-in date (YYYY-MM-DD)",
        openapi_extra={"format": "date", "example": "2026-02-14"},
    ),
    checkOut: date = Query(
        ...,
        description="Check-out date (YYYY-MM-DD)",
        openapi_extra={"format": "date", "example": "2026-02-15"},
    ),
    pageNumber: int = Query(1, ge=1, description="Page number (default 1)"),
    sort: str = Query("BEST_VALUE", description="Sort option (e.g., BEST_VALUE)"),
    adults: int = Query(2, ge=1, le=20, description="Number of adults"),
    rooms: int = Query(1, ge=1, le=10, description="Number of rooms"),
    currencyCode: str = Query("LKR", min_length=3, max_length=3, description="Currency code (e.g., LKR,USD)"),
    rating: Optional[int] = Query(None, ge=0, le=5, description="Minimum rating filter"),
    priceMin: Optional[int] = Query(None, ge=0, description="Minimum price filter"),
    priceMax: Optional[int] = Query(None, ge=0, description="Maximum price filter"),

    # Arrays: Swagger sends these as repeated keys:
    # childrenAges=5&childrenAges=9
    childrenAges: Optional[List[int]] = Query(None, description="Children ages(0-17)"),
    amenity: Optional[List[str]] = Query(None, description="Amenities"),
    neighborhood: Optional[List[str]] = Query(None, description="Neighborhoods"),
    deals: Optional[List[str]] = Query(None, description="Deals"),
    type_: Optional[List[str]] = Query(None, description="Hotel types"),
    class_: Optional[List[str]] = Query(None, alias="class", description="Hotel classes"),
    style: Optional[List[str]] = Query(None, description="Styles"),
    brand: Optional[List[str]] = Query(None, description="Brands"),
):
    # CheckIn and CheckOut validation
    if checkOut <= checkIn:
        raise HTTPException(status_code=422, detail="checkOut must be after checkIn")

    try:
        # returns a JSON
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
            type_=type_,
            class_=class_,
            style=style,
            brand=brand,
        )

    except RapidAPIError as e:
        # Preserve the upstream status code + payload for debugging
        raise HTTPException(status_code=e.status_code, detail={"message": str(e), "upstream": e.payload})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Internal server error", "error": repr(e)})
