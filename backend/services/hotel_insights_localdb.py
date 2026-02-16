# backend/services/hotel_local_db.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.hotel import Hotel


async def search_hotels_local(
    *,
    db: AsyncSession,
    location: str,
    limit: int = 20,
    rating: Optional[int] = None,
    priceMin: Optional[int] = None,
    priceMax: Optional[int] = None,
    amenity: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Exploratory hotel search from local database.
    No live prices. No RapidAPI.
    """

    filters = [Hotel.location.ilike(f"%{location}%")]

    if rating:
        filters.append(Hotel.rating >= rating)

    if priceMin:
        filters.append(Hotel.price >= priceMin)

    if priceMax:
        filters.append(Hotel.price <= priceMax)

    # Basic query
    stmt = select(Hotel).where(and_(*filters)).limit(limit)

    result = await db.execute(stmt)
    hotels = result.scalars().all()

    # Convert ORM objects → dict
    return [serialize_hotel(h) for h in hotels]


def serialize_hotel(hotel: Hotel) -> Dict[str, Any]:
    """
    Convert ORM model to API-friendly dictionary.
    """
    return {
        "id": hotel.id,
        "name": hotel.name,
        "location": hotel.location,
        "rating": hotel.rating,
        "price": hotel.price,
        "amenities": hotel.amenities,
        "source": "local_db",
    }
