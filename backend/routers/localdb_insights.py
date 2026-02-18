from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.services.hotel_insights_localdb import get_hotel_insights_localdb

router = APIRouter(prefix="/localdb", tags=["Local Data"])


@router.get("/hotels/insights")
async def hotels_insights_localdb(
    location: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    rating: Optional[int] = Query(None, ge=0, le=5),
    priceMin: Optional[int] = Query(None, ge=0),
    priceMax: Optional[int] = Query(None, ge=0),
    user_request: str = Query("Find the best value hotel for me.", description="Natural-language preference"),
):
    if priceMin is not None and priceMax is not None and priceMin > priceMax:
        raise HTTPException(422, "priceMin must be less than or equal to priceMax")

    try:
        return get_hotel_insights_localdb(
            location=location,
            user_request=user_request,
            limit=limit,
            rating=rating,
            priceMin=priceMin,
            priceMax=priceMax,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": repr(e)})
