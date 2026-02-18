from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "hotels.db"
# Extract numeric amount from values like "LKR 25,000"
_PRICE_RE = re.compile(r"(\d[\d,]*)")


# -------------------------
# DB / parsing helpers
# -------------------------
def _open_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _extract_price_number(price_text: Optional[str]) -> Optional[int]:
    # Parse first number-like token from price_range text
    if not price_text:
        return None
    match = _PRICE_RE.search(price_text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def serialize_hotel(row: sqlite3.Row) -> Dict[str, Any]:
    # Convert DB row -> API-friendly shape used by app responses
    return {
        "id": row["id"],
        "name": row["name"],
        "location": row["city"],
        "rating": row["avg_review"],
        "price": row["price_range"],
        "source": "local_db",
    }


async def search_hotels_local(
    *,
    location: str,
    limit: int = 20,
    rating: Optional[int] = None,
    priceMin: Optional[int] = None,
    priceMax: Optional[int] = None,
    db: Any = None,
) -> List[Dict[str, Any]]:
    # NOTE: db param kept only for compatibility with older call sites
    filters = ["active = 1", "LOWER(city) LIKE LOWER(?)"]
    params: List[Any] = [f"%{location}%"]

    if rating is not None:
        filters.append("avg_review >= ?")
        params.append(rating)

    where_sql = " AND ".join(filters)
    sql = (
        "SELECT id, name, city, price_range, avg_review "
        f"FROM hotels WHERE {where_sql} "
        # Better entries first
        "ORDER BY avg_review DESC, review_count DESC "
        "LIMIT ?"
    )

    # Pull a wider set first, then apply Python-side price filter
    query_limit = max(limit * 4, limit)
    params.append(query_limit)

    try:
        with _open_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []

    filtered_hotels: List[Dict[str, Any]] = []
    for row in rows:
        hotel = serialize_hotel(row)

        # price_range is text, so do numeric filtering in Python
        if priceMin is not None or priceMax is not None:
            numeric_price = _extract_price_number(hotel["price"])
            if numeric_price is None:
                continue
            if priceMin is not None and numeric_price < priceMin:
                continue
            if priceMax is not None and numeric_price > priceMax:
                continue

        filtered_hotels.append(hotel)
        if len(filtered_hotels) >= limit:
            break

    return filtered_hotels


def get_hotel_insights_localdb(
    *,
    location: str,
    user_request: str = "Find the best value hotel for me.",
    limit: int = 20,
    rating: Optional[int] = None,
    priceMin: Optional[int] = None,
    priceMax: Optional[int] = None,
) -> Dict[str, Any]:
    # Same retrieval/filter logic, wrapped with metadata for decision engine
    filters = ["active = 1", "LOWER(city) LIKE LOWER(?)"]
    params: List[Any] = [f"%{location}%"]

    if rating is not None:
        filters.append("avg_review >= ?")
        params.append(rating)

    where_sql = " AND ".join(filters)
    sql = (
        "SELECT id, name, city, price_range, avg_review "
        f"FROM hotels WHERE {where_sql} "
        "ORDER BY avg_review DESC, review_count DESC "
        "LIMIT ?"
    )

    query_limit = max(limit * 4, limit)
    params.append(query_limit)

    try:
        with _open_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        hotels: List[Dict[str, Any]] = []
    else:
        hotels = []
        for row in rows:
            hotel = serialize_hotel(row)

            if priceMin is not None or priceMax is not None:
                numeric_price = _extract_price_number(hotel["price"])
                if numeric_price is None:
                    continue
                if priceMin is not None and numeric_price < priceMin:
                    continue
                if priceMax is not None and numeric_price > priceMax:
                    continue

            hotels.append(hotel)
            if len(hotels) >= limit:
                break

    return {
        "source": "local_db",
        "user_request": user_request,
        "count": len(hotels),
        "results": hotels,
        "meta": {
            "location": location,
        },
    }
