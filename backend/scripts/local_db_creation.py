"""
This script creates/updates a local SQLite database with hotel data for Sri Lanka cities using the TripAdvisor API via RapidAPI
"""
from __future__ import annotations

import json
import os
import re # For regular expression based price extraction (e.g. "LKR 25,000" -> 25000)
import sqlite3 
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests # For making HTTP calls to RapidAPI
from dotenv import load_dotenv

load_dotenv()

# -------------------------
# Hardcoded Sri Lanka GeoIDs (no location search calls)
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
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "hotels.db"  # this file go back 2 levels to backend/data/hotels.db

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY") or os.getenv("X_RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "tripadvisor16.p.rapidapi.com")

# How many hotels per city to store
DEFAULT_LIMIT_PER_CITY = 25

# Gives time to be ready for the next city retival (RapidAPI usually ok without, but this avoids spikes)
SLEEP_BETWEEN_CALLS_SEC = float(os.getenv("INGEST_SLEEP_SEC", "0.2"))



# DB helpers
def _get_conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False) # check_same_thread=False allows sharing connection across CPU threads
    conn.row_factory = sqlite3.Row # allows dict-like access to rows (e.g. row["name"] instead of row[0])

    # Pragmas: Rules for how SQLite should operate
    conn.execute("PRAGMA foreign_keys = ON;") # enforce foreign keys (SQLite doesn't default)
    conn.execute("PRAGMA journal_mode = WAL;") # reads and writes can happen parallelly
    conn.execute("PRAGMA synchronous = NORMAL;") # Balance between write speed and crash safety 
    conn.execute("PRAGMA temp_store = MEMORY;") # temporary tables stored in RAM instead of disk.
    conn.execute("PRAGMA cache_size = -20000;")  # ~20MB cache in RAM (negative means KB, so -20000 = 20MB)
    conn.execute("PRAGMA busy_timeout = 3000;") # wait up to 3 seconds if DB is locked

    return conn


def init_db(db_path: Path) -> None:
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

        # Indexes (allow fast lookup instead of scanning entire table)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_city ON hotels(city);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_price_range ON hotels(price_range);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_avg_review ON hotels(avg_review);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_review_count ON hotels(review_count);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_active ON hotels(active);")
        conn.commit() # Permanently saves changes to the database


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False) if obj is not None else "null" # ensure_ascii=False allows unicode characters to be stored properly

# Insert or update hotel record (if id conflict)
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
        row, # get values from the dict using named parameters (e.g. :name in sqlite replaced by row["name"])
    )


def count_hotels(conn: sqlite3.Connection) -> int:
    r = conn.execute("SELECT COUNT(*) AS n FROM hotels;").fetchone() # 
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
    # Generate dates: If updating later, consider changing the days for non busy dates to get accurate price data
    checkin_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
    checkout_date = (datetime.now() + timedelta(days=6)).strftime("%Y-%m-%d")
    
    url = f"{BASE_URL}/api/v1/hotels/searchHotels"
    params = {
        "geoId": str(geo_id),
        "checkIn": checkin_date,      # 5 days from now
        "checkOut": checkout_date,    # 6 days from now
        "adults": "2",
        "rooms": "1",
        "currencyCode": "LKR",        
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
    
    return hotels


def _clean_title(title: str) -> str:
    # RapidAPI gives titles like "1. Abode Bombay" sometimes
    return re.sub(r"^\s*\d+\.\s*", "", title).strip() # removes leading "1. ", "2. " etc from title


def _derive_amenities(primary_info: Optional[str]) -> List[str]:
    """
    Get amenities from PrimaryInfo text. The API doesn't give structured amenities everytime
    """
    if not primary_info:
        return []

    s = primary_info.lower()
    tags: List[str] = [primary_info.strip()]
    if "breakfast" in s:
        tags.append("breakfast")
    if "free" in s:
        tags.append("free")
    if "wifi" in s:
        tags.append("wifi")
    return list(dict.fromkeys(tags))  # Remove duplicate amenities while maintaing original order (e.g. ["free", "wifi", "free"] → ["free", "wifi"])


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
    if RAPIDAPI_KEY:
        checkin = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        checkout = (datetime.now() + timedelta(days=6)).strftime("%Y-%m-%d")
        print(f"Search dates: {checkin} to {checkout}")
        print(f"Currency: LKR\n")
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