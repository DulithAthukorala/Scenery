"""
Normalize the TripAdvisor JSON API response to a smaller, more LLM-friendly format that keeps only the relevant info for ranking and explanation.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_get(d: dict, path: list[str], default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default # default can be None or something else if we want("msg not found" etc)
        cur = cur[k] # cur["bubbleRating"] -> cur["rating"]
    return cur


def normalize_tripadvisor_hotels(raw: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    """
    Turn the giant RapidAPI response into a small, LLM-friendly list.
    Keep only what helps ranking and explanation.
    """

    # Data Retrieval For TripAdvisor API
    data = raw.get("data") or raw.get("data", {}) # handle "data": null / 0 etc
    hotels = data.get("data") if isinstance(data, dict) else raw.get("data", []) # handle nested "data" Dicts
    if not isinstance(hotels, list):
        hotels = []

    out: List[Dict[str, Any]] = [] # [{"title": "Hotel A", "rating": 4.5, "price": 30000},]

    for h in hotels[:limit]:
        if not isinstance(h, dict):
            continue

        title = h.get("title") or h.get("name")
        rating = _safe_get(h, ["bubbleRating", "rating"])
        reviews = _safe_get(h, ["bubbleRating", "count"])
        price = h.get("priceForDisplay") or _safe_get(h, ["price", "display"])
        provider = h.get("provider")
        is_sponsored = h.get("isSponsored")


        out.append(
            {
                "title": title,
                "rating": rating,
                "reviews": reviews,
                "price": price,
                "provider": provider,
                "isSponsored": is_sponsored,
            }
        )

    return out
