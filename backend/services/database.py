"""
Database initialization and access functions.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "hotels.db"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # check_same_thread=False
    # Allow SQLite to be use any thread in the same worker in FastAPI threadpool
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row # row["name"] can be used instead of row[3]

    # Pragmas for future performance (if didin't move to Postgres etc)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;") # Better concurrency
    conn.execute("PRAGMA synchronous = NORMAL;") # balanced speed and safety when writing
    conn.execute("PRAGMA temp_store = MEMORY;") # Temp data in memory
    conn.execute("PRAGMA cache_size = -20000;")  # ~20MB cache
    conn.execute("PRAGMA busy_timeout = 3000;")  # 3s wait if DB is locked without error

    return conn


def init_db() -> None:
    """
    Local hotel table.
    (id, name, city are required. Other fields are optional and can be null)
    """
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hotels (
                -- TripAdvisor hotel id (string)
                id TEXT PRIMARY KEY,

                -- Display fields
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                district TEXT,
                address TEXT,

                -- Local price Range (manual)
                price_range TEXT,

                -- Ratings
                avg_review REAL,
                review_count INTEGER,

                -- RapidAPI extra fields
                primary_info TEXT,
                secondary_info TEXT,
                provider TEXT,
                is_sponsored INTEGER DEFAULT 0,

                -- JSON blobs
                amenities_json TEXT,
                images_json TEXT,
                badge_json TEXT,
                raw_json TEXT,

                description TEXT,

                active INTEGER DEFAULT 1,
                featured INTEGER DEFAULT 0,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # Helpful indexes for fast filtering/ranking
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_city ON hotels(city);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_price ON hotels(price_range);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_avg_review ON hotels(avg_review);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_review_count ON hotels(review_count);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_hotels_active ON hotels(active);")

        conn.commit()


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False) if obj is not None else "null"


def _load(s: Optional[str], default: Any) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def upsert_hotel(h: Dict[str, Any]) -> None:
    """
    Upsert one hotel row.

    Expected input shape (flexible):
    - You can pass "name" or "title"
    - images can be list[str] or list[dict] etc
    - badge can be dict
    - raw can store the raw provider payload
    """
    hotel_id = str(h.get("id") or "").strip()
    if not hotel_id:
        raise ValueError("Hotel upsert requires 'id'")

    name = (h.get("name") or h.get("title") or "").strip()
    if not name:
        raise ValueError("Hotel upsert requires 'name' or 'title'")

    row = {
        "id": hotel_id,
        "name": name,
        "city": (h.get("city") or "").strip(),
        "district": h.get("district"),
        "address": h.get("address"),
        "latitude": h.get("latitude"),
        "longitude": h.get("longitude"),
        "price_lkr": h.get("price_lkr"),
        "price_range": h.get("price_range"),
        "star_rating": h.get("star_rating"),
        "avg_review": h.get("avg_review"),
        "review_count": h.get("review_count"),
        "primary_info": h.get("primaryInfo") or h.get("primary_info"),
        "secondary_info": h.get("secondaryInfo") or h.get("secondary_info"),
        "provider": h.get("provider"),
        "is_sponsored": int(bool(h.get("isSponsored") if "isSponsored" in h else h.get("is_sponsored"))),
        "amenities_json": _dump(h.get("amenities", [])),
        "images_json": _dump(h.get("images", h.get("cardPhotos", []))),
        "badge_json": _dump(h.get("badge", {})),
        "raw_json": _dump(h.get("raw")),
        "description": h.get("description"),
        "active": int(h.get("active", 1)),
        "featured": int(h.get("featured", 0)),
    }

    if not row["city"]:
        # For a cache DB, we still want a city. If missing, default to "Unknown".
        row["city"] = "Unknown"

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO hotels (
                id, name, city, district, address, latitude, longitude,
                price_lkr, price_range,
                star_rating, avg_review, review_count,
                primary_info, secondary_info, provider, is_sponsored,
                amenities_json, images_json, badge_json, raw_json,
                description, active, featured, last_updated
            ) VALUES (
                :id, :name, :city, :district, :address, :latitude, :longitude,
                :price_lkr, :price_range,
                :star_rating, :avg_review, :review_count,
                :primary_info, :secondary_info, :provider, :is_sponsored,
                :amenities_json, :images_json, :badge_json, :raw_json,
                :description, :active, :featured, CURRENT_TIMESTAMP
            )
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                city=excluded.city,
                district=excluded.district,
                address=excluded.address,
                latitude=excluded.latitude,
                longitude=excluded.longitude,
                price_lkr=excluded.price_lkr,
                price_range=excluded.price_range,
                star_rating=excluded.star_rating,
                avg_review=excluded.avg_review,
                review_count=excluded.review_count,
                primary_info=excluded.primary_info,
                secondary_info=excluded.secondary_info,
                provider=excluded.provider,
                is_sponsored=excluded.is_sponsored,
                amenities_json=excluded.amenities_json,
                images_json=excluded.images_json,
                badge_json=excluded.badge_json,
                raw_json=excluded.raw_json,
                description=excluded.description,
                active=excluded.active,
                featured=excluded.featured,
                last_updated=CURRENT_TIMESTAMP
            ;
            """,
            row,
        )
        conn.commit()


def _row_to_dict(r: sqlite3.Row) -> Dict[str, Any]:
    d = dict(r)

    d["amenities"] = _load(d.get("amenities_json"), [])
    d["images"] = _load(d.get("images_json"), [])
    d["badge"] = _load(d.get("badge_json"), {})
    d["raw"] = _load(d.get("raw_json"), None)

    # Keep DB-only json fields out of API response
    d.pop("amenities_json", None)
    d.pop("images_json", None)
    d.pop("badge_json", None)
    d.pop("raw_json", None)

    return d


def search_hotels_local(
    *,
    city: str,
    max_price: Optional[int] = None,
    min_rating: Optional[float] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Basic local search used for "exploratory" queries.
    (When dates exist, you still call RapidAPI for live pricing.)
    """
    q = """
        SELECT *
        FROM hotels
        WHERE active = 1
          AND city = ?
    """
    params: List[Any] = [city]

    if max_price is not None:
        q += " AND (price_lkr IS NULL OR price_lkr <= ?)"
        params.append(max_price)

    if min_rating is not None:
        q += " AND (avg_review IS NULL OR avg_review >= ?)"
        params.append(min_rating)

    q += " ORDER BY featured DESC, avg_review DESC, review_count DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()

    return [_row_to_dict(r) for r in rows]


def count_hotels() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM hotels;").fetchone()
    return int(row["n"] if row else 0)
