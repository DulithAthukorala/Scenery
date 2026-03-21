"""
POST /voice/room

Creates a Daily.co room, generates meeting tokens (user + bot),
starts the Pipecat bot container, and returns the room URL + user token
to the browser.
"""
from __future__ import annotations

import logging
import time
from typing import Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import DAILY_API_KEY, DAILY_BOT_URL

router = APIRouter(prefix="/voice", tags=["voice-webrtc"])
logger = logging.getLogger(__name__)

DAILY_API_BASE = "https://api.daily.co/v1"


# ─────────────────────────────────────────────────────────────────────────────
#  Schemas
# ─────────────────────────────────────────────────────────────────────────────

class RoomRequest(BaseModel):
    session_id: Optional[str] = None


class RoomResponse(BaseModel):
    room_url: str
    token: str
    session_id: str
    room_name: str


# ─────────────────────────────────────────────────────────────────────────────
#  Daily.co helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _create_daily_room(session_id: str) -> dict:
    """Create an ephemeral Daily room with a 1-hour TTL."""
    # Use a unique room name each call so that re-opening the page never
    # clashes with an existing room (Daily rejects duplicate names).
    room_suffix = uuid4().hex[:10]
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DAILY_API_BASE}/rooms",
            headers={"Authorization": f"Bearer {DAILY_API_KEY}"},
            json={
                "name": f"scenery-{room_suffix}",
                "properties": {
                    "exp": int(time.time()) + 3600,
                    "max_participants": 2,
                    "enable_chat": False,
                    "start_audio_off": False,
                    "start_video_off": True,
                },
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def _create_meeting_token(room_name: str, is_owner: bool = False) -> str:
    """Create a meeting token for the room."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DAILY_API_BASE}/meeting-tokens",
            headers={"Authorization": f"Bearer {DAILY_API_KEY}"},
            json={
                "properties": {
                    "room_name": room_name,
                    "is_owner": is_owner,
                    "exp": int(time.time()) + 3600,
                },
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()["token"]


async def _start_bot(room_url: str, session_id: str, bot_token: str) -> None:
    """Tell the Pipecat bot runner to start a pipeline for this room."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DAILY_BOT_URL}/start",
            json={
                "room_url": room_url,
                "session_id": session_id,
                "bot_token": bot_token,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        logger.info("bot_started room_url=%s session_id=%s", room_url, session_id)


# ─────────────────────────────────────────────────────────────────────────────
#  Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/room", response_model=RoomResponse)
async def create_voice_room(payload: RoomRequest):
    """
    Creates a Daily room, starts the Pipecat bot, and returns credentials
    for the browser to join via the Daily JS SDK.
    """
    if not DAILY_API_KEY:
        raise HTTPException(status_code=503, detail="DAILY_API_KEY not configured")
    if not DAILY_BOT_URL:
        raise HTTPException(status_code=503, detail="DAILY_BOT_URL not configured")

    session_id = (payload.session_id or "").strip() or str(uuid4())

    try:
        room_data = await _create_daily_room(session_id)
        room_url: str = room_data["url"]
        room_name: str = room_data["name"]

        # User token (viewer) and bot token (owner with full control)
        user_token = await _create_meeting_token(room_name, is_owner=False)
        bot_token = await _create_meeting_token(room_name, is_owner=True)

        await _start_bot(room_url, session_id, bot_token)

        return RoomResponse(
            room_url=room_url,
            token=user_token,
            session_id=session_id,
            room_name=room_name,
        )

    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        logger.error("daily_api_error status=%s body=%s", exc.response.status_code, exc.response.text)
        raise HTTPException(status_code=502, detail=f"Daily API error: {exc.response.status_code}")
    except Exception as exc:
        logger.exception("create_voice_room_failed")
        raise HTTPException(status_code=500, detail=str(exc))
