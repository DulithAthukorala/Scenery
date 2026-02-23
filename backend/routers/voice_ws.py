from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.config import ELEVEN_API_KEY, ELEVEN_STT_MODEL_ID, ELEVEN_STT_SAMPLE_RATE
from backend.services.eleven_stt import ElevenLabsSTT, ElevenSTTConfig

router = APIRouter(prefix="/voice", tags=["voice"])


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()

    if not ELEVEN_API_KEY:
        await websocket.send_json({"type": "error", "message": "ELEVEN_API_KEY missing"})
        await websocket.close()
        return

    audio_q: asyncio.Queue[Optional[bytes]] = asyncio.Queue()

    async def audio_chunks() -> AsyncIterator[bytes]:
        while True:
            chunk = await audio_q.get()
            if chunk is None:
                break
            yield chunk

    async def receiver_from_client():
        try:
            while True:
                chunk = await websocket.receive_bytes()
                await audio_q.put(chunk)
        except WebSocketDisconnect:
            pass
        finally:
            await audio_q.put(None)  # triggers final commit inside STT client

    recv_task = asyncio.create_task(receiver_from_client())

    try:
        stt = ElevenLabsSTT(
            ElevenSTTConfig(
                api_key=ELEVEN_API_KEY,
                model_id=ELEVEN_STT_MODEL_ID,
                sample_rate=ELEVEN_STT_SAMPLE_RATE,
            )
        )

        async for event in stt.stream_transcripts(audio_chunks()):
            await websocket.send_json({"type": "stt_event", "event": event})

    finally:
        recv_task.cancel()