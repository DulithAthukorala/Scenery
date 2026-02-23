from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/voice", tags=["voice"])


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    """
    Client connects, then sends binary audio chunks.
    Server will later reply with transcript events.
    """
    await websocket.accept()

    try:
        # For now: just prove we receive chunks.
        while True:
            chunk: bytes = await websocket.receive_bytes()
            # temporary debug: tell client we got data
            await websocket.send_json({"type": "debug", "bytes_received": len(chunk)})

    except WebSocketDisconnect:
        # Client closed the connection
        return