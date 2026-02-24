from __future__ import annotations

import asyncio
import inspect
import logging
import time
from contextlib import suppress
from typing import AsyncIterator, Optional, Callable, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocketState

from backend.config import ELEVEN_API_KEY, ELEVEN_STT_MODEL_ID, ELEVEN_STT_SAMPLE_RATE
from backend.services.eleven_stt import ElevenLabsSTT, ElevenSTTConfig
import backend.core.decision as decision_mod  # ✅ dynamic access

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger(__name__)


def _get_decision_fn() -> Callable[[str], Any]:
    # ✅ tries common names so we stop guessing
    for name in ("handle_query", "decide", "route_query", "run_decision"):
        fn = getattr(decision_mod, name, None)
        if callable(fn):
            return fn
    raise AttributeError("No decision function found in backend/core/decision.py")


async def _safe_send_json(websocket: WebSocket, payload: dict, *, label: str) -> bool:
    if websocket.application_state != WebSocketState.CONNECTED:
        logger.warning("skip_send_socket_not_connected label=%s", label)
        return False
    try:
        await websocket.send_json(payload)
        return True
    except WebSocketDisconnect:
        logger.info("send_failed_client_disconnected label=%s", label)
        return False
    except RuntimeError:
        logger.exception("send_failed_runtime_error label=%s", label)
        return False
    except Exception:
        logger.exception("send_failed_unexpected label=%s", label)
        return False


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("voice_stream_connected")

    if not ELEVEN_API_KEY:
        await _safe_send_json(websocket, {"type": "error", "message": "ELEVEN_API_KEY missing"}, label="missing_api_key")
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close()
        return

    audio_q: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
    latest_text = ""
    client_audio_done = asyncio.Event()
    client_disconnected = asyncio.Event()
    decision_called = False

    async def call_decision_and_respond(final_text: str) -> None:
        nonlocal decision_called
        if decision_called:
            return
        decision_called = True

        await _safe_send_json(websocket, {"type": "server_debug", "message": "about_to_call_decision"}, label="debug_about_to_call_decision")

        started = time.perf_counter()
        payload: dict
        try:
            logger.info("about_to_call_decision text=%r", final_text)
            decision_fn = _get_decision_fn()
            result = decision_fn(final_text)
            if inspect.isawaitable(result):
                result = await result
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("decision_completed elapsed_ms=%d", elapsed_ms)
            payload = {
                "type": "assistant_response",
                "result": jsonable_encoder(result),
                "meta": {"decision_ms": elapsed_ms, "status": "ok"},
            }
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.exception("decision_call_failed elapsed_ms=%d", elapsed_ms)
            payload = {
                "type": "assistant_response",
                "result": {
                    "action": "ERROR",
                    "message": "Decision layer failed while processing transcript.",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                "meta": {"decision_ms": elapsed_ms, "status": "error"},
            }

        sent = await _safe_send_json(websocket, payload, label="assistant_response")
        if sent:
            await _safe_send_json(
                websocket,
                {"type": "server_debug", "message": "assistant_response_sent"},
                label="debug_assistant_response_sent",
            )

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

                # ✅ End-of-audio marker (your test client sends b"")
                if chunk == b"":
                    client_audio_done.set()
                    logger.info("received_end_of_audio_marker")
                    break

                await audio_q.put(chunk)

        except WebSocketDisconnect:
            client_disconnected.set()
            logger.info("client_disconnected_while_receiving")
        finally:
            await audio_q.put(None)

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
            msg_type = (event or {}).get("message_type")

            if msg_type == "partial_transcript":
                latest_text = (event.get("text") or "").strip()
                await _safe_send_json(websocket, {"type": "partial_text", "text": latest_text}, label="partial_text")
                continue

            if msg_type in ("committed_transcript", "final_transcript"):
                latest_text = (event.get("text") or "").strip()
                if latest_text:
                    await _safe_send_json(websocket, {"type": "final_text", "text": latest_text}, label="final_text")
                    if client_audio_done.is_set() and not decision_called:
                        await call_decision_and_respond(latest_text)
                        break
                continue

            # keep debug
            await _safe_send_json(websocket, {"type": "stt_event", "event": event}, label="stt_event")

        final_text = latest_text.strip()
        if not final_text:
            await _safe_send_json(websocket, {"type": "error", "message": "No transcript captured from audio."}, label="no_transcript")
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close()
            return

        await _safe_send_json(websocket, {"type": "final_text", "text": final_text}, label="final_text_post_stream")

        if not decision_called:
            await call_decision_and_respond(final_text)

        # Keep socket open briefly so clients reliably receive the last frame,
        # then close if still connected.
        try:
            await asyncio.wait_for(client_disconnected.wait(), timeout=1.5)
        except asyncio.TimeoutError:
            pass

        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close(code=1000)
            logger.info("voice_stream_closed_normally")

    except Exception as e:
        logger.exception("voice_ws_error")
        try:
            await _safe_send_json(
                websocket,
                {"type": "error", "message": f"voice_ws error: {type(e).__name__}: {e}"},
                label="voice_ws_error",
            )
        except Exception:
            pass
        try:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close(code=1011)
        except Exception:
            pass

    finally:
        recv_task.cancel()
        with suppress(asyncio.CancelledError):
            await recv_task
        logger.info("voice_stream_finished")