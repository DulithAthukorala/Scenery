from __future__ import annotations

import logging
import time
from uuid import uuid4
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.core.decision import handle_query
from backend.services.conversation_memory import get_session_context, save_session_turn

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


def _extract_response_text(payload: Dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    ranking = data.get("ranking") if isinstance(data.get("ranking"), dict) else {}

    llm_response = ranking.get("llm_response")
    if isinstance(llm_response, str) and llm_response.strip():
        return llm_response.strip()

    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()

    return "I couldn't generate a response right now. Please try again."


def _extract_hotels(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    ranking = data.get("ranking") if isinstance(data.get("ranking"), dict) else {}

    ranked_hotels = ranking.get("ranked_hotels")
    if isinstance(ranked_hotels, list):
        return ranked_hotels

    results = data.get("results")
    if isinstance(results, list):
        return results

    return []


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/chat")
async def chat_query(payload: ChatRequest, request: Request, response: Response):
    req_start = time.perf_counter()
    user_query = payload.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    mode = payload.mode if payload.mode in ("text", "voice") else "text"
    cookie_session_id = (request.cookies.get("session_id") or "").strip()
    session_id = (payload.session_id or "").strip() or cookie_session_id or str(uuid4())

    logger.info("chat_query_received mode=%s session_id=%s", mode, session_id)
    session_context = await get_session_context(session_id)
    decision_result = await handle_query(user_query, mode=mode, context=session_context)
    total_ms = round((time.perf_counter() - req_start) * 1000, 2)
    response.headers["X-Total-Ms"] = str(total_ms)
    response.headers["X-Action"] = str(decision_result.get("action", "UNKNOWN"))
    response.headers["X-Session-Id"] = session_id
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=60 * 60 * 24,
        httponly=False,
        samesite="lax",
    )

    timing = decision_result.get("timing")
    if isinstance(timing, dict) and timing.get("total_ms") is not None:
        response.headers["X-Decision-Ms"] = str(timing.get("total_ms"))

    response_text = _extract_response_text(decision_result)
    hotels = _extract_hotels(decision_result)

    persisted_context = await save_session_turn(
        session_id=session_id,
        user_text=user_query,
        assistant_text=response_text,
        result_payload=decision_result,
        existing_context=session_context,
    )

    api_result = {
        **decision_result,
        "response": response_text,
        "hotels": hotels,
        "session_id": session_id,
        "conversation_id": persisted_context.get("conversation_id"),
        "memory": {
            "enabled": bool(persisted_context.get("memory_enabled")),
            "turn_events": len(persisted_context.get("turns") or []),
        },
    }

    logger.info(
        "chat_query_done action=%s total_ms=%.2f",
        decision_result.get("action", "UNKNOWN"),
        total_ms,
    )
    return api_result
