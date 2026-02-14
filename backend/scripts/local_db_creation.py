# backend/scripts/local_db_creation.py
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# -------------------------
# Hardcoded Sri Lanka GeoIDs (no location search calls)
# Picked as "top tourism" style set based on your list.
# You can add/remove cities freely without changing logic.
# -------------------------
CITY_GEOIDS: Dict[str, int] = {
    "Colombo": 293962,
    "Kandy": 304138,
    "Galle": 189825,
    "Ella": 616035,
    "Nuwara Eliya": 608524,
    "Sigiriya": 304141,
    "Mirissa": 1407334,
    "Negombo": 297897,
    "Trincomalee": 424963,
    "Arugam Bay": 3348959,
    "Jaffna": 304135,
    "Hambantota": 424962,
    "Anuradhapura": 304132,
    "Polonnaruwa": 304139,
    "Chilaw": 447558,
}

BASE_URL = "https://tripadvisor16.p.rapidapi.com"
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "hotels.db"

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY") or os.getenv("X_RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "tripadvisor16.p.rapidapi.com")

# How many hotels per city to store
DEFAULT_LIMIT_PER_CITY = int(os.getenv("INGEST_LIMIT_PER_CITY", "25"))

# Basic rate safety (RapidAPI usually ok without, but this avoids spikes)
SLEEP_BETWEEN_CALLS_SEC = float(os.getenv("INGEST_SLEEP_SEC", "0.2"))


# -------------------------
# DB helpers
# -------------------------
def _get_conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Pragmas: good defaults for a small app
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = -20000;")  # ~20MB cache
    conn.execute("PRAGMA busy_timeout = 3000;")

    return conn


def init_db(db_path: Path) -> None:
    """
    Creates the simplified schema YOU asked for.
    No district/address/lat/long/images/badge/featured/created_at/updated_at.
    """
    with _get_conn(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hotels (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                city TEXT NOT NULL,

                price_range TEXT,

                avg_review REAL,
                review_count INTEGER,

                primary_info TEXT,
                secondary_info TEXT,

                provider TEXT,
                is_sponsored INTEGER DEFAULT 0,

                amenities_json TEXT,
                description TEXT,

                active INTEGER DEFAULT 1,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_city ON hotels(city);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_price_range ON hotels(price_range);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_avg_review ON hotels(avg_review);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_review_count ON hotels(review_count);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_active ON hotels(active);")
        conn.commit()


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False) if obj is not None else "null"


def upsert_hotel(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO hotels (
            id, name, city,
            price_range,
            avg_review, review_count,
            primary_info, secondary_info,
            provider, is_sponsored,
            amenities_json, description,
            active, last_updated
        ) VALUES (
            :id, :name, :city,
            :price_range,
            :avg_review, :review_count,
            :primary_info, :secondary_info,
            :provider, :is_sponsored,
            :amenities_json, :description,
            :active, CURRENT_TIMESTAMP
        )
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            city=excluded.city,
            price_range=excluded.price_range,
            avg_review=excluded.avg_review,
            review_count=excluded.review_count,
            primary_info=excluded.primary_info,
            secondary_info=excluded.secondary_info,
            provider=excluded.provider,
            is_sponsored=excluded.is_sponsored,
            amenities_json=excluded.amenities_json,
            description=excluded.description,
            active=excluded.active,
            last_updated=CURRENT_TIMESTAMP
        ;
        """,
        row,
    )


def count_hotels(conn: sqlite3.Connection) -> int:
    r = conn.execute("SELECT COUNT(*) AS n FROM hotels;").fetchone()
    return int(r["n"] if r else 0)


# -------------------------
# RapidAPI call
# -------------------------
def _headers() -> Dict[str, str]:
    if not RAPIDAPI_KEY:
        raise RuntimeError(
            "Missing RAPIDAPI_KEY in your environment. Put it in .env and load it, or set it in terminal."
        )
    return {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }


def fetch_hotels_for_city(geo_id: int) -> List[Dict[str, Any]]:
    # Generate dates: 5 days from now and 6 days from now
    checkin_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
    checkout_date = (datetime.now() + timedelta(days=6)).strftime("%Y-%m-%d")
    
    url = f"{BASE_URL}/api/v1/hotels/searchHotels"
    params = {
        "geoId": str(geo_id),
        "checkIn": checkin_date,      # 5 days from now
        "checkOut": checkout_date,    # 6 days from now
        "adults": "2",
        "rooms": "1",
        "currencyCode": "LKR",        # FIXED: Use currencyCode not currency
        "sort": "BEST_VALUE",
    }

    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()

    # Check for API errors
    if not payload.get("status", False):
        print(f"  API Error: {payload.get('message', 'Unknown error')}")
        return []

    data = payload.get("data", {})
    hotels = data.get("data", [])
    
    if not isinstance(hotels, list):
        return []
    
    # Debug: Check first hotel's price info
    if hotels and len(hotels) > 0:
        first_hotel = hotels[0]
        print(f"  Sample hotel price fields:")
        print(f"    - priceForDisplay: {first_hotel.get('priceForDisplay')}")
        print(f"    - strikethroughPrice: {first_hotel.get('strikethroughPrice')}")
        if 'commerceInfo' in first_hotel:
            commerce = first_hotel['commerceInfo']
            if isinstance(commerce.get('priceForDisplay'), dict):
                print(f"    - commerceInfo.priceForDisplay.text: {commerce['priceForDisplay'].get('text')}")
            else:
                print(f"    - commerceInfo.priceForDisplay: {commerce.get('priceForDisplay')}")
    
    return hotels


# -------------------------
# Normalize (match your RapidAPI shape)
# -------------------------
_money_re = re.compile(r"([A-Za-z]{0,3})\s*([\d,]+)")


def _clean_title(title: str) -> str:
    # RapidAPI gives titles like "1. Abode Bombay" sometimes
    return re.sub(r"^\s*\d+\.\s*", "", title).strip()


def _derive_amenities(primary_info: Optional[str]) -> List[str]:
    """
    Important truth:
    - RapidAPI searchHotels response does NOT reliably provide full amenities.
    So we store a lightweight derived list so it's not always empty.
    Later, if you want real amenities, you'd need a hotel-details endpoint per hotel (more API calls).
    """
    if not primary_info:
        return []
    # Keep it simple: store the phrase + a few tags if recognizable
    s = primary_info.lower()
    tags: List[str] = [primary_info.strip()]
    if "breakfast" in s:
        tags.append("breakfast")
    if "free" in s:
        tags.append("free")
    if "wifi" in s:
        tags.append("wifi")
    return list(dict.fromkeys(tags))  # de-dupe, keep order


def normalize_hotel(raw: Dict[str, Any], city: str) -> Dict[str, Any]:
    hotel_id = str(raw.get("id") or "").strip()
    if not hotel_id:
        raise ValueError("Hotel missing id")

    title = (raw.get("title") or "").strip()
    name = _clean_title(title) if title else "Unknown"

    bubble = raw.get("bubbleRating") or {}
    avg_review = bubble.get("rating")
    review_count_raw = bubble.get("count")
    # review_count might be "(51)" or "1,037" depending on endpoint version
    review_count: Optional[int] = None
    if isinstance(review_count_raw, str):
        digits = re.sub(r"[^\d]", "", review_count_raw)
        if digits:
            review_count = int(digits)

    primary_info = raw.get("primaryInfo")
    secondary_info = raw.get("secondaryInfo")
    provider = raw.get("provider")
    is_sponsored = int(bool(raw.get("isSponsored", False)))

    # Price extraction - check multiple locations
    price_range = None
    
    # First try: direct priceForDisplay
    price_for_display = raw.get("priceForDisplay")
    if isinstance(price_for_display, str) and price_for_display:
        price_range = price_for_display
    
    # Second try: commerceInfo.priceForDisplay (could be string or dict)
    if not price_range and "commerceInfo" in raw:
        commerce = raw["commerceInfo"]
        commerce_price = commerce.get("priceForDisplay")
        if isinstance(commerce_price, str) and commerce_price:
            price_range = commerce_price
        elif isinstance(commerce_price, dict):
            # Sometimes it's a dict with 'text' key
            price_range = commerce_price.get("text")


    amenities = _derive_amenities(primary_info if isinstance(primary_info, str) else None)

    # optional short description: combine primary + secondary (if exists)
    desc_parts = []
    if isinstance(primary_info, str) and primary_info.strip():
        desc_parts.append(primary_info.strip())
    if isinstance(secondary_info, str) and secondary_info.strip():
        desc_parts.append(secondary_info.strip())
    description = " - ".join(desc_parts) if desc_parts else None

    return {
        "id": hotel_id,
        "name": name,
        "city": city,

        "price_range": price_range,

        "avg_review": float(avg_review) if isinstance(avg_review, (int, float)) else None,
        "review_count": review_count,

        "primary_info": primary_info if isinstance(primary_info, str) else None,
        "secondary_info": secondary_info if isinstance(secondary_info, str) else None,

        "provider": provider if isinstance(provider, str) else None,
        "is_sponsored": is_sponsored,

        "amenities_json": _dump(amenities),
        "description": description,

        "active": 1,
    }


# -------------------------
# Main ingestion
# -------------------------
def ingest(db_path: Path, limit_per_city: int) -> None:
    # Print API key status (first 5 and last 5 chars for security)
    if RAPIDAPI_KEY:
        key_preview = f"{RAPIDAPI_KEY[:5]}...{RAPIDAPI_KEY[-5:]}"
        print(f"[INFO] Using API Key: {key_preview}")
        print(f"[INFO] API Host: {RAPIDAPI_HOST}")
        
        # Show the dates we're using
        checkin = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        checkout = (datetime.now() + timedelta(days=6)).strftime("%Y-%m-%d")
        print(f"[INFO] Search dates: {checkin} to {checkout}")
        print(f"[INFO] Currency: LKR\n")
    else:
        print("[ERROR] No API key found!")
        return
    
    init_db(db_path)

    with _get_conn(db_path) as conn:
        before = count_hotels(conn)
        stored_total = 0

        for city, geo_id in CITY_GEOIDS.items():
            print(f"[INFO] {city}: geoId={geo_id}")

            try:
                hotels = fetch_hotels_for_city(geo_id)
            except Exception as e:
                print(f"[ERROR] {city}: failed to fetch hotels: {e}")
                continue

            if not hotels:
                print(f"[WARN] {city}: 0 hotels returned")
                continue

            # keep only top N
            hotels = hotels[:limit_per_city]

            stored_city = 0
            for raw in hotels:
                try:
                    row = normalize_hotel(raw, city=city)
                    upsert_hotel(conn, row)
                    stored_city += 1
                except Exception as e:
                    # don't break the whole city because one record is weird
                    print(f"[WARN] {city}: skip hotel due to normalize/upsert error: {e}")

            conn.commit()
            stored_total += stored_city
            print(f"[OK] {city}: stored {stored_city} hotels")
            time.sleep(SLEEP_BETWEEN_CALLS_SEC)

        after = count_hotels(conn)

    print(f"\n{'='*60}")
    print(f"[DONE] Ingest complete. Added/updated ~{stored_total} rows")
    print(f"DB: {db_path}")
    print(f"Rows before: {before}  |  Rows after: {after}")
    print(f"{'='*60}")


if __name__ == "__main__":
    limit = DEFAULT_LIMIT_PER_CITY
    ingest(DB_PATH, limit_per_city=limit)