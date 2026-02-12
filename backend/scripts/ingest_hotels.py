"""
Ingest ~150-250 hotels into local SQLite from TripAdvisor RapidAPI.

Run from project root:
  python -m backend.scripts.ingest_hotels

Requires:
  - backend/config.py loads RAPIDAPI_KEY, RAPIDAPI_HOST
  - backend/services/database.py exposes DB_PATH (Path or str)
  - DB already initialized (tables created)
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from backend.config import RAPIDAPI_KEY, RAPIDAPI_HOST
from backend.services.database import DB_PATH  # your upgraded database.py exports this


BASE_URL = "https://tripadvisor16.p.rapidapi.com"


# Top 10 tourism-heavy places in Sri Lanka (practical list for your DB seed)
TOP_10_CITIES_SL = [
    "Colombo",
    "Kandy",
    "Galle",
    "Ella",
    "Nuwara Eliya",
    "Sigiriya",
    "Mirissa",
    "Negombo",
    "Trincomalee",
    "Arugam Bay",
]


@dataclass
class HotelRow:
    source_hotel_id: str
    name: str
    city: str
    district: Optional[str]
    avg_review: Optional[float]
    review_count: Optional[int]
    provider: Optional[str]
    primary_info: Optional[str]
    secondary_info: Optional[str]
    photo_templates: List[str]
    raw: Dict[str, Any]


class IngestError(RuntimeError):
    pass


def _headers() -> Dict[str, str]:
    if not RAPIDAPI_KEY or not RAPIDAPI_HOST:
        raise IngestError("Missing RAPIDAPI_KEY or RAPIDAPI_HOST in environment/config.")
    return {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Accept": "application/json",
    }


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"^\d+\.\s*", "", text)  # remove leading "1. "
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:80] if len(text) > 80 else text


def _safe_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, str):
        s = re.sub(r"[^\d]", "", x)
        return int(s) if s else None
    return None


def _safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
        (name,),
    )
    return cur.fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table});")
    return [row[1] for row in cur.fetchall()]  # row[1] = column name


async def _search_location_geo_id(client: httpx.AsyncClient, query: str) -> Optional[str]:
    """
    GET /api/v1/hotels/searchLocation?query=...
    Returns geoId as string or None.
    """
    url = f"{BASE_URL}/api/v1/hotels/searchLocation"
    r = await client.get(url, headers=_headers(), params={"query": query})
    if r.status_code >= 400:
        return None

    payload = r.json()
    data = payload.get("data") or payload.get("data", [])
    if not isinstance(data, list) or not data:
        return None

    # Try to pick result that mentions Sri Lanka in name/details if present
    best = None
    for item in data:
        if not isinstance(item, dict):
            continue
        text = " ".join(
            str(item.get(k, "") or "")
            for k in ("title", "name", "location", "secondaryInfo", "geoName")
        ).lower()
        if "sri lanka" in text:
            best = item
            break

    if best is None:
        best = data[0]

    geo_id = best.get("geoId") or best.get("geo_id") or best.get("locationId")
    return str(geo_id) if geo_id else None


async def _search_hotels_raw(
    client: httpx.AsyncClient,
    *,
    geo_id: str,
    check_in: date,
    check_out: date,
    page_number: int = 1,
    adults: int = 2,
    rooms: int = 1,
    sort: str = "BEST_VALUE",
    currency_code: str = "LKR",
) -> Dict[str, Any]:
    """
    GET /api/v1/hotels/searchHotels
    """
    url = f"{BASE_URL}/api/v1/hotels/searchHotels"
    params: List[Tuple[str, str]] = [
        ("geoId", geo_id),
        ("checkIn", check_in.isoformat()),
        ("checkOut", check_out.isoformat()),
        ("pageNumber", str(page_number)),
        ("sort", sort),
        ("adults", str(adults)),
        ("rooms", str(rooms)),
        ("currencyCode", currency_code),
    ]
    r = await client.get(url, headers=_headers(), params=params)
    if r.status_code >= 400:
        raise IngestError(f"RapidAPI searchHotels failed {r.status_code}: {r.text[:200]}")
    return r.json()


def _normalize_hotels(raw: Dict[str, Any], city: str, limit: int) -> List[HotelRow]:
    """
    Normalize RapidAPI response -> list of HotelRow
    """
    data = raw.get("data") or raw.get("data", {})
    hotels = data.get("data") if isinstance(data, dict) else raw.get("data", [])
    if not isinstance(hotels, list):
        hotels = []

    out: List[HotelRow] = []

    for h in hotels[:limit]:
        if not isinstance(h, dict):
            continue

        hid = str(h.get("id") or "").strip()
        if not hid:
            continue

        title = (h.get("title") or h.get("name") or "").strip()
        title = re.sub(r"^\d+\.\s*", "", title).strip()
        if not title:
            continue

        bubble = h.get("bubbleRating") if isinstance(h.get("bubbleRating"), dict) else {}
        rating = _safe_float(bubble.get("rating"))
        reviews = _safe_int(bubble.get("count"))

        provider = (h.get("provider") or None)
        primary = (h.get("primaryInfo") or None)
        secondary = (h.get("secondaryInfo") or None)

        photo_templates: List[str] = []
        photos = h.get("cardPhotos")
        if isinstance(photos, list):
            for p in photos:
                if not isinstance(p, dict):
                    continue
                sizes = p.get("sizes")
                if isinstance(sizes, dict):
                    tpl = sizes.get("urlTemplate")
                    if isinstance(tpl, str) and tpl:
                        photo_templates.append(tpl)

        out.append(
            HotelRow(
                source_hotel_id=hid,
                name=title,
                city=city,
                district=secondary,  # you can later map properly; for now it's useful
                avg_review=rating,
                review_count=reviews,
                provider=provider,
                primary_info=primary,
                secondary_info=secondary,
                photo_templates=photo_templates,
                raw=h,
            )
        )

    return out


def _upsert_into_db(conn: sqlite3.Connection, row: HotelRow) -> None:
    """
    Inserts/updates into whatever schema exists.
    - If your DB has hotels.slug -> use that for de-dupe
    - If hotel_sources exists -> store tripadvisor mapping
    - If hotel_images exists -> store images
    """
    hotels_cols = _columns(conn, "hotels")
    now = datetime.utcnow().isoformat(timespec="seconds")

    slug = _slugify(f"{row.name}-{row.city}")

    # Build hotel insert payload based on existing columns
    payload: Dict[str, Any] = {}
    if "name" in hotels_cols:
        payload["name"] = row.name
    elif "title" in hotels_cols:
        payload["title"] = row.name

    if "slug" in hotels_cols:
        payload["slug"] = slug

    if "city" in hotels_cols:
        payload["city"] = row.city

    if "district" in hotels_cols:
        payload["district"] = row.district

    if "avg_review" in hotels_cols:
        payload["avg_review"] = row.avg_review
    elif "rating" in hotels_cols:
        payload["rating"] = row.avg_review

    if "review_count" in hotels_cols:
        payload["review_count"] = row.review_count
    elif "reviews" in hotels_cols:
        payload["reviews"] = row.review_count

    if "description" in hotels_cols:
        # combine primary/secondary as a placeholder “snippet”
        snippet = " • ".join([s for s in [row.primary_info, row.secondary_info] if s])
        payload["description"] = snippet or None

    if "updated_at" in hotels_cols:
        payload["updated_at"] = now
    if "created_at" in hotels_cols:
        payload.setdefault("created_at", now)

    # Decide how to identify existing hotel row
    hotel_id: Optional[int] = None

    # 1) If slug exists, use it
    if "slug" in hotels_cols:
        cur = conn.execute("SELECT id FROM hotels WHERE slug=? LIMIT 1;", (slug,))
        hit = cur.fetchone()
        if hit:
            hotel_id = int(hit[0])

    # 2) fallback: name+city
    if hotel_id is None and ("name" in hotels_cols or "title" in hotels_cols) and "city" in hotels_cols:
        name_col = "name" if "name" in hotels_cols else "title"
        cur = conn.execute(
            f"SELECT id FROM hotels WHERE {name_col}=? AND city=? LIMIT 1;",
            (row.name, row.city),
        )
        hit = cur.fetchone()
        if hit:
            hotel_id = int(hit[0])

    # Insert or update
    if hotel_id is None:
        cols = ", ".join(payload.keys())
        qs = ", ".join(["?"] * len(payload))
        conn.execute(f"INSERT INTO hotels ({cols}) VALUES ({qs});", tuple(payload.values()))
        hotel_id = int(conn.execute("SELECT last_insert_rowid();").fetchone()[0])
    else:
        sets = ", ".join([f"{k}=?" for k in payload.keys() if k != "created_at"])
        vals = [payload[k] for k in payload.keys() if k != "created_at"]
        if sets:
            conn.execute(f"UPDATE hotels SET {sets} WHERE id=?;", (*vals, hotel_id))

    # hotel_sources mapping (if table exists)
    if _table_exists(conn, "hotel_sources"):
        src_cols = _columns(conn, "hotel_sources")
        # expected columns (from our recommended schema):
        # hotel_id, source, source_hotel_id, last_synced_at, source_url
        source = "tripadvisor"
        mapping: Dict[str, Any] = {}
        if "hotel_id" in src_cols:
            mapping["hotel_id"] = hotel_id
        if "source" in src_cols:
            mapping["source"] = source
        if "source_hotel_id" in src_cols:
            mapping["source_hotel_id"] = row.source_hotel_id
        if "last_synced_at" in src_cols:
            mapping["last_synced_at"] = now
        if "source_url" in src_cols:
            # not always available; keep blank
            mapping["source_url"] = None

        # upsert-ish behavior
        cur = conn.execute(
            "SELECT 1 FROM hotel_sources WHERE hotel_id=? AND source=? LIMIT 1;",
            (hotel_id, source),
        ).fetchone()

        if cur:
            # update
            if "source_hotel_id" in mapping:
                conn.execute(
                    "UPDATE hotel_sources SET source_hotel_id=?, last_synced_at=? WHERE hotel_id=? AND source=?;",
                    (row.source_hotel_id, now, hotel_id, source),
                )
        else:
            cols = ", ".join(mapping.keys())
            qs = ", ".join(["?"] * len(mapping))
            conn.execute(
                f"INSERT INTO hotel_sources ({cols}) VALUES ({qs});",
                tuple(mapping.values()),
            )

    # hotel_images (if table exists)
    if _table_exists(conn, "hotel_images") and row.photo_templates:
        img_cols = _columns(conn, "hotel_images")

        # Clear existing images for this hotel to keep it simple & consistent
        if "hotel_id" in img_cols:
            conn.execute("DELETE FROM hotel_images WHERE hotel_id=?;", (hotel_id,))

        for idx, tpl in enumerate(row.photo_templates):
            mapping: Dict[str, Any] = {}
            if "hotel_id" in img_cols:
                mapping["hotel_id"] = hotel_id
            if "url" in img_cols:
                mapping["url"] = tpl
            elif "url_template" in img_cols:
                mapping["url_template"] = tpl

            if "sort_order" in img_cols:
                mapping["sort_order"] = idx

            if "created_at" in img_cols:
                mapping["created_at"] = now

            if mapping:
                cols = ", ".join(mapping.keys())
                qs = ", ".join(["?"] * len(mapping))
                conn.execute(f"INSERT INTO hotel_images ({cols}) VALUES ({qs});", tuple(mapping.values()))


async def main() -> None:
    # Choose a dummy date range for seeding (RapidAPI expects dates even if prices null)
    check_in = date.today() + timedelta(days=30)
    check_out = check_in + timedelta(days=2)

    db_path = str(DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    if not _table_exists(conn, "hotels"):
        raise IngestError("Table 'hotels' does not exist. Run init_db first.")

    total_inserted = 0
    per_city_limit = 25  # 10 cities * 25 = 250 (you can reduce later)
    pages = 1            # keep 1 page to control API calls

    async with httpx.AsyncClient(timeout=30) as client:
        for city in TOP_10_CITIES_SL:
            geo_id = await _search_location_geo_id(client, city)
            if not geo_id:
                print(f"[WARN] geoId not found for {city}, skipping.")
                continue

            print(f"[INFO] {city}: geoId={geo_id}")

            city_rows: List[HotelRow] = []
            for page in range(1, pages + 1):
                raw = await _search_hotels_raw(
                    client,
                    geo_id=geo_id,
                    check_in=check_in,
                    check_out=check_out,
                    page_number=page,
                )
                city_rows.extend(_normalize_hotels(raw, city=city, limit=per_city_limit))

            # Deduplicate within city by source_hotel_id
            seen = set()
            unique_rows = []
            for r in city_rows:
                if r.source_hotel_id in seen:
                    continue
                seen.add(r.source_hotel_id)
                unique_rows.append(r)

            # Insert/update
            before = total_inserted
            for r in unique_rows[:per_city_limit]:
                _upsert_into_db(conn, r)
                total_inserted += 1

            conn.commit()
            print(f"[OK] {city}: stored {total_inserted - before} hotels")

    conn.close()
    print(f"\n[DONE] Ingest complete. Total stored/updated rows: {total_inserted}")
    print(f"DB: {db_path}")


if __name__ == "__main__":
    asyncio.run(main())
