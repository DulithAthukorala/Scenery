"""
This module implements hotel data retrieval from a local SQLite database (includes raw -> normalized -> retrival)
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "hotels.db"
# re compile amounts from values like "LKR 25,000"
_PRICE_RE = re.compile(r"(\d[\d,]*)")
_LUXURY_HINT_RE = re.compile(r"\b(luxury|premium|upscale|high[-\s]?end|5[-\s]?star|five[-\s]?star)\b", re.IGNORECASE)
_FAMILY_HINT_RE = re.compile(r"\b(family[-\s]?friendly|family|kids?|children|child)\b", re.IGNORECASE)


# DB helpers
def _open_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row # allows dict-like access to rows (e.g. row["name"] instead of row[0])
    return conn

# Price parsing (Needs changing when price ranges are added to the DB) (usage as well)
def _extract_price_number(price_text: Optional[str]) -> Optional[int]:
    # Parse first number-like token from price_range text
    if not price_text:
        return None
    match = _PRICE_RE.search(price_text) # 
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _safe_text(value: Any) -> str:
    if isinstance(value, str):
        return value.lower()
    return ""


def _preference_score(row: sqlite3.Row, user_request: str) -> int:
    request = user_request or ""
    wants_luxury = bool(_LUXURY_HINT_RE.search(request))
    wants_family = bool(_FAMILY_HINT_RE.search(request))

    if not (wants_luxury or wants_family):
        return 0

    content_parts = [
        _safe_text(row["name"]),
        _safe_text(row["primary_info"]),
        _safe_text(row["secondary_info"]),
        _safe_text(row["description"]),
    ]

    amenities_raw = row["amenities_json"]
    if isinstance(amenities_raw, str) and amenities_raw.strip():
        try:
            amenities_obj = json.loads(amenities_raw)
            if isinstance(amenities_obj, list):
                content_parts.append(" ".join(str(item).lower() for item in amenities_obj))
            else:
                content_parts.append(str(amenities_obj).lower())
        except (TypeError, json.JSONDecodeError):
            content_parts.append(amenities_raw.lower())

    content = " ".join(part for part in content_parts if part)
    if not content:
        return 0

    score = 0
    if wants_luxury:
        score += len(_LUXURY_HINT_RE.findall(content))
    if wants_family:
        score += len(_FAMILY_HINT_RE.findall(content))
    return score

# Convert DB to standardized dict format and remove unnecessary fields (faster llm ranking)
def serialize_hotel(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "location": row["city"],
        "rating": row["avg_review"],
        "price": row["price_range"],
        "source": "local_db",
    }

# * -> search_hotels(geoID=...,) not searchHotels(...,)
# db param kept for future extensibility if we want to swap out SQLite for something else
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
        "SELECT id, name, city, price_range, avg_review, review_count, primary_info, secondary_info, description, amenities_json "
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
        ranked_hotels: List[tuple[int, float, int, Dict[str, Any]]] = []
        for row in rows:
            hotel = serialize_hotel(row) # remove unnecessary fields/ DICT conversion

            if priceMin is not None or priceMax is not None:
                numeric_price = _extract_price_number(hotel["price"])
                if numeric_price is None:
                    continue
                if priceMin is not None and numeric_price < priceMin:
                    continue
                if priceMax is not None and numeric_price > priceMax:
                    continue

            pref_score = _preference_score(row, user_request)
            rating_value = float(row["avg_review"] or 0.0)
            review_count = int(row["review_count"] or 0)
            ranked_hotels.append((pref_score, rating_value, review_count, hotel))

        ranked_hotels.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        hotels = [item[3] for item in ranked_hotels[:limit]]

    return {
        "source": "local_db",
        "user_request": user_request,
        "count": len(hotels),
        "results": hotels,
        "meta": {
            "location": location,
        },
    }
