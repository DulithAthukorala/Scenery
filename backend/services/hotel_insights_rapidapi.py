from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from backend.services.hotel_raw_json import search_hotels
from backend.services.hotel_normalize import normalize_tripadvisor_hotels

from google import genai
from backend.config import GEMINI_API_KEY, GEMINI_MODEL

client = genai.Client(api_key=GEMINI_API_KEY)


def _build_prompt(
    normalized_hotels: List[Dict[str, Any]],
    user_request: str,
) -> str:
    # Keep it strict: we want JSON back.
    return f"""
You are Scenery, a travel assistant.
Given hotel candidates, rank them for the user's request.

USER REQUEST:
{user_request}

HOTEL CANDIDATES (JSON):
{json.dumps(normalized_hotels, ensure_ascii=False)} # ensure_ascii=False to keep keep non-English chars as they are

Return ONLY valid JSON with this exact schema:
{{
  "top_picks": [
    {{
      "title": "string",
      "rank": 1,
      "why": ["reason1", "reason2", "reason3"],
      "tradeoffs": ["tradeoff1", "tradeoff2"],
      "confidence": 0.0
    }}
  ],
  "quick_summary": "string",
  "notes": ["string"]
}}

Rules:
- Do NOT invent hotels not in the candidates list.
- Prefer value (rating + price + reviews) unless user request says otherwise.
- If some fields are missing, say so in tradeoffs/notes.
- Keep "top_picks" to max 5.
""".strip()


async def get_hotel_insights(
    *,
    geoId: str,
    checkIn,
    checkOut,
    pageNumber: int = 1,
    sort: str = "BEST_VALUE",
    adults: int = 2,
    rooms: int = 1,
    currencyCode: str = "LKR",
    rating: Optional[int] = None,
    priceMin: Optional[int] = None,
    priceMax: Optional[int] = None,
    amenity: Optional[List[str]] = None,
    neighborhood: Optional[List[str]] = None,
    deals: Optional[List[str]] = None,
    type_: Optional[List[str]] = None,
    class_: Optional[List[str]] = None,
    style: Optional[List[str]] = None,
    brand: Optional[List[str]] = None,
    user_request: str = "Find the best value hotel for me.",
) -> Dict[str, Any]:
    # 1) Call RapidAPI
    raw = await search_hotels(
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
    )

    # 2) Normalize
    hotels = normalize_tripadvisor_hotels(raw, limit=10)

    # 3) Ask Gemini
    prompt = _build_prompt(hotels, user_request)

    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    text = resp.text or ""
    # best-effort JSON parse (LLMs sometimes add whitespace)
    try:
        insights = json.loads(text)
    except Exception:
        insights = {"raw": text, "parse_error": True}

    return {
        "insights": insights,
        "candidates_used": hotels,
        "meta": {"model": GEMINI_MODEL},
    }
