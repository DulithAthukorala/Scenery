from __future__ import annotations

import asyncio
import json
import inspect
import logging
import time
from contextlib import suppress
from typing import AsyncIterator, Optional, Callable, Any
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocketState

from backend.config import ELEVEN_API_KEY, ELEVEN_STT_MODEL_ID, ELEVEN_STT_SAMPLE_RATE
from backend.config import ELEVEN_TTS_VOICE_ID, ELEVEN_TTS_MODEL_ID, ELEVEN_TTS_STABILITY
from backend.config import ELEVEN_TTS_SIMILARITY_BOOST, ELEVEN_TTS_OPTIMIZE_LATENCY
from backend.services.eleven_stt import ElevenLabsSTT, ElevenSTTConfig
from backend.services.eleven_tts import ElevenLabsTTS, ElevenTTSConfig
from backend.services.conversation_memory import get_session_context, save_session_turn
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


def _extract_response_text(payload: dict) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    ranking = data.get("ranking") if isinstance(data.get("ranking"), dict) else {}

    llm_response = ranking.get("llm_response")
    if isinstance(llm_response, str) and llm_response.strip():
        return llm_response.strip()

    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()

    return "I couldn't generate a response right now. Please try again."


def _extract_hotels(payload: dict) -> list:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    ranking = data.get("ranking") if isinstance(data.get("ranking"), dict) else {}

    ranked_hotels = ranking.get("ranked_hotels")
    if isinstance(ranked_hotels, list):
        return ranked_hotels

    results = data.get("results")
    if isinstance(results, list):
        return results

    return []


@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()
    session_id = (websocket.query_params.get("session_id") or "").strip() or str(uuid4())
    session_context = await get_session_context(session_id)
    logger.info("voice_stream_connected session_id=%s", session_id)

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
        nonlocal decision_called, session_context
        if decision_called:
            return
        decision_called = True

        await _safe_send_json(websocket, {"type": "server_debug", "message": "about_to_call_decision"}, label="debug_about_to_call_decision")

        started = time.perf_counter()
        payload: dict
        try:
            logger.info("about_to_call_decision text=%r", final_text)
            decision_fn = _get_decision_fn()
            result = decision_fn(final_text, mode="voice", context=session_context)
            if inspect.isawaitable(result):
                result = await result

            response_text = _extract_response_text(result)
            hotels = _extract_hotels(result)
            session_context = await save_session_turn(
                session_id=session_id,
                user_text=final_text,
                assistant_text=response_text,
                result_payload=result,
                existing_context=session_context,
            )

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("decision_completed elapsed_ms=%d", elapsed_ms)
            payload = {
                "type": "assistant_response",
                "result": jsonable_encoder(
                    {
                        **result,
                        "response": response_text,
                        "hotels": hotels,
                        "session_id": session_id,
                        "conversation_id": session_context.get("conversation_id"),
                        "memory": {
                            "enabled": bool(session_context.get("memory_enabled")),
                            "turn_events": len(session_context.get("turns") or []),
                        },
                    }
                ),
                "meta": {
                    "decision_ms": elapsed_ms,
                    "status": "ok",
                    "session_id": session_id,
                    "conversation_id": session_context.get("conversation_id"),
                    "memory_enabled": bool(session_context.get("memory_enabled")),
                },
            }
            
            # Send text response first
            sent = await _safe_send_json(websocket, payload, label="assistant_response")
            if sent:
                await _safe_send_json(
                    websocket,
                    {"type": "server_debug", "message": "assistant_response_sent"},
                    label="debug_assistant_response_sent",
                )
                
                # Now send TTS audio response
                try:
                    await _safe_send_json(websocket, {"type": "tts_start"}, label="tts_start")
                    
                    tts = ElevenLabsTTS(
                        ElevenTTSConfig(
                            api_key=ELEVEN_API_KEY,
                            voice_id=ELEVEN_TTS_VOICE_ID,
                            model_id=ELEVEN_TTS_MODEL_ID,
                            stability=ELEVEN_TTS_STABILITY,
                            similarity_boost=ELEVEN_TTS_SIMILARITY_BOOST,
                            optimize_streaming_latency=ELEVEN_TTS_OPTIMIZE_LATENCY,
                        )
                    )
                    
                    async for event in tts.stream_audio(response_text):
                        msg_type = event.get("message_type")
                        
                        if msg_type == "audio":
                            audio_data = event.get("audio", "")
                            await _safe_send_json(
                                websocket,
                                {"type": "tts_audio", "audio": audio_data},
                                label="tts_audio_chunk"
                            )
                        elif msg_type == "flush":
                            await _safe_send_json(websocket, {"type": "tts_end"}, label="tts_end")
                            break
                        elif msg_type == "error":
                            logger.error("tts_error: %s", event.get("error"))
                            await _safe_send_json(
                                websocket,
                                {"type": "tts_error", "error": event.get("error")},
                                label="tts_error"
                            )
                            break
                            
                    logger.info("tts_completed")
                except Exception as tts_exc:
                    logger.exception("tts_generation_failed")
                    await _safe_send_json(
                        websocket,
                        {"type": "tts_error", "error": str(tts_exc)},
                        label="tts_exception"
                    )
                    
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
                message = await websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    client_disconnected.set()
                    break

                if message.get("bytes") is not None:
                    chunk = message.get("bytes") or b""
                    if chunk == b"":
                        client_audio_done.set()
                        logger.info("received_end_of_audio_marker")
                        break
                    await audio_q.put(chunk)
                    continue

                if message.get("text") is not None:
                    try:
                        payload = json.loads(message.get("text") or "{}")
                    except json.JSONDecodeError:
                        payload = {}

                    if payload.get("type") == "audio_end":
                        client_audio_done.set()
                        logger.info("received_audio_end_text_message")
                        break

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