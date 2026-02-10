from __future__ import annotations

from datetime import date
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from backend.services.hotel_insights import get_hotel_insights
from backend.services.tripadvisor_rapidapi import RapidAPIError

router = APIRouter(prefix="/tripadvisor", tags=["tripadvisor-ai"])


@router.get("/hotels/insights")
async def hotels_insights(
    geoId: str = Query(...),
    checkIn: date = Query(..., openapi_extra={"format": "date", "example": "2026-02-14"}),
    checkOut: date = Query(..., openapi_extra={"format": "date", "example": "2026-02-15"}),
    pageNumber: int = Query(1, ge=1),
    sort: str = Query("BEST_VALUE"),
    adults: int = Query(2, ge=1, le=20),
    rooms: int = Query(1, ge=1, le=10),
    currencyCode: str = Query("LKR", min_length=3, max_length=3),
    rating: Optional[int] = Query(None, ge=0, le=5),
    priceMin: Optional[int] = Query(None, ge=0),
    priceMax: Optional[int] = Query(None, ge=0),

    amenity: Optional[List[str]] = Query(None),
    neighborhood: Optional[List[str]] = Query(None),
    deals: Optional[List[str]] = Query(None),
    type_: Optional[List[str]] = Query(None, alias="type"),
    class_: Optional[List[str]] = Query(None, alias="class"),
    style: Optional[List[str]] = Query(None),
    brand: Optional[List[str]] = Query(None),

    user_request: str = Query("Find the best value hotel for me.", description="Natural-language preference"),
):
    if checkOut <= checkIn:
        raise HTTPException(422, "checkOut must be after checkIn")

    try:
        return await get_hotel_insights(
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
            user_request=user_request,
        )
    except RapidAPIError as e:
        raise HTTPException(status_code=e.status_code, detail={"message": str(e), "upstream": e.payload})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": repr(e)})
