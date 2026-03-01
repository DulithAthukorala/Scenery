from __future__ import annotations

import logging
from uuid import uuid4
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.core.decision import handle_query
from backend.services.conversation_memory import get_session_context, save_session_turn

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: Optional[str] = None
    session_id: Optional[str] = None
    force_mode: Optional[str] = None
    preset_location: Optional[str] = None
    preset_dates: Optional[dict] = None
    rerank_hotels: Optional[list] = None  # For re-ranking existing hotels without calling RapidAPI


@router.post("/chat")
async def chat_query(payload: ChatRequest, request: Request, response: Response):
    user_query = payload.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    mode = payload.mode if payload.mode in ("text", "voice") else "text"
    session_id = (payload.session_id or "").strip() \
        or (request.cookies.get("session_id") or "").strip() \
        or str(uuid4())

    logger.info("chat_query_received mode=%s session_id=%s", mode, session_id)

    # 1. Load conversation context & run the decision engine
    session_context = await get_session_context(session_id)
    decision_result = await handle_query(
        user_query, 
        mode=mode, 
        force_mode=payload.force_mode,
        preset_location=payload.preset_location,
        preset_dates=payload.preset_dates,
        rerank_hotels=payload.rerank_hotels,
        context=session_context
    )

    # 2. Pull the LLM response text and hotel list from the result
    data = decision_result.get("data") or {}
    ranking = data.get("ranking") or {}
    response_text = ranking.get("llm_response", "").strip() or decision_result.get("message", "")
    hotels = ranking.get("ranked_hotels") or data.get("results") or []

    # 3. Save this turn to conversation memory
    persisted_context = await save_session_turn(
        session_id=session_id,
        user_text=user_query,
        assistant_text=response_text,
        result_payload=decision_result,
        existing_context=session_context,
    )

    # 4. Set session cookie so the browser remembers the session
    response.set_cookie(key="session_id", value=session_id, max_age=86400, httponly=False, samesite="lax")

    logger.info("chat_query_done action=%s", decision_result.get("action"))

    return {
        **decision_result,
        "response": response_text,
        "hotels": hotels,
        "session_id": session_id,
        "conversation_id": persisted_context.get("conversation_id"),
    }
