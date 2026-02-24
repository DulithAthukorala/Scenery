from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.decision import handle_query

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    mode: Optional[str] = None


@router.post("/chat")
async def chat_query(payload: ChatRequest):
    user_query = payload.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="query must not be empty")

    mode = payload.mode if payload.mode in ("text", "voice") else "text"
    logger.info("chat_query_received mode=%s", mode)
    return await handle_query(user_query, mode=mode)
