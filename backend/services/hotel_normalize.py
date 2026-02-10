from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_get(d: dict, path: list[str], default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def normalize_tripadvisor_hotels(raw: Dict[str, Any], limit: int = 15) -> List[Dict[str, Any]]:
    """
    Turn the giant RapidAPI response into a small, LLM-friendly list.
    Keep only what helps ranking and explanation.
    """
    data = raw.get("data") or raw.get("data", {})
    hotels = data.get("data") if isinstance(data, dict) else raw.get("data", [])
    if not isinstance(hotels, list):
        hotels = []

    out: List[Dict[str, Any]] = []

    for h in hotels[:limit]:
        if not isinstance(h, dict):
            continue

        title = h.get("title") or h.get("name")
        rating = _safe_get(h, ["bubbleRating", "rating"])
        reviews = _safe_get(h, ["bubbleRating", "count"])
        price = h.get("priceForDisplay") or _safe_get(h, ["price", "display"])
        provider = h.get("provider")
        is_sponsored = h.get("isSponsored")

        # sometimes there are coordinates / address fields (varies by endpoint)
        primary = h.get("primaryInfo")
        secondary = h.get("secondaryInfo")

        out.append(
            {
                "title": title,
                "rating": rating,
                "reviews": reviews,
                "price": price,
                "provider": provider,
                "primaryInfo": primary,
                "secondaryInfo": secondary,
                "isSponsored": is_sponsored,
            }
        )

    return out
