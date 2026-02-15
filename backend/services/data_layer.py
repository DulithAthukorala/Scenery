# backend/services/data_layer.py
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional, Protocol, Literal


Source = Literal["local_db", "rapidapi"]


# --- Contracts (so you can swap implementations easily) ---

class LocalHotelRepo(Protocol):
    async def search_hotels(
        self,
        location: str,
        *,
        limit: int = 20,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Exploratory search from your local DB (no live pricing)."""


class RapidAPIClient(Protocol):
    async def search_hotels_live(
        self,
        location: str,
        *,
        check_in: date,
        check_out: date,
        limit: int = 20,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Live search (prices/availability). Requires dates."""


# --- Decision result ---

@dataclass
class DataLayerResult:
    source: Source
    results: list[dict[str, Any]]
    fallback_used: bool = False


# --- Heuristics: detect whether query implies dates ---

_MONTHS = r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)"
_DATE_PATTERNS = [
    re.compile(r"\b\d{1,2}\s*[-/]\s*\d{1,2}\b", re.IGNORECASE),     # 15-17, 15/17 (range-ish)
    re.compile(r"\b\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{2,4}\b"),   # 15-02-2026
    re.compile(rf"\b{_MONTHS}\s+\d{{1,2}}\b", re.IGNORECASE),       # feb 15
    re.compile(rf"\b\d{{1,2}}\s+{_MONTHS}\b", re.IGNORECASE),       # 15 feb
    re.compile(r"\b(check\s?in|check\s?out|from|to|until)\b", re.IGNORECASE),
    re.compile(r"\b(today|tomorrow|tonight|next\s+week|next\s+month|this\s+weekend)\b", re.IGNORECASE),
]

def query_mentions_dates(text: Optional[str]) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    return any(p.search(t) for p in _DATE_PATTERNS)


# --- The Smart Data Layer ---

class SmartHotelDataLayer:
    """
    Rules:
      1) If user provides dates OR query implies dates -> RapidAPI (live).
      2) Else -> Local DB first (exploratory).
      3) If Local DB returns 0 -> fallback to RapidAPI (ONLY if dates exist or you can infer them).
         (For Day 2, we do fallback only when dates are provided; otherwise return empty/local.)
    """

    def __init__(self, local_repo: LocalHotelRepo, rapid_client: RapidAPIClient):
        self.local_repo = local_repo
        self.rapid_client = rapid_client

    async def search(
        self,
        *,
        location: str,
        query_text: Optional[str] = None,
        check_in: Optional[date] = None,
        check_out: Optional[date] = None,
        limit: int = 20,
        filters: Optional[dict[str, Any]] = None,
    ) -> DataLayerResult:

        needs_live = (check_in is not None and check_out is not None) or query_mentions_dates(query_text)

        # 1) Live request if dates are present (strong signal)
        if check_in and check_out:
            results = await self.rapid_client.search_hotels_live(
                location, check_in=check_in, check_out=check_out, limit=limit, filters=filters
            )
            return DataLayerResult(source="rapidapi", results=results)

        # 2) Exploratory -> local DB first
        local_results = await self.local_repo.search_hotels(location, limit=limit, filters=filters)

        if local_results:
            return DataLayerResult(source="local_db", results=local_results)

        # 3) Fallback rule
        # If query implies dates but user didn't provide exact check-in/out,
        # don't guess dates silently in a "production" app.
        # So: only fallback when dates are explicitly provided.
        if needs_live:
            return DataLayerResult(source="local_db", results=[], fallback_used=False)

        return DataLayerResult(source="local_db", results=[], fallback_used=False)
