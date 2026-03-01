from __future__ import annotations

import asyncio
import json
import inspect
import logging
import time
from contextlib import suppress
from typing import AsyncIterator, Optional, Callable, Any, Dict
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
import backend.core.decision as decision_mod

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger(__name__)

# ── Constants ──
STT_TIMEOUT_SECONDS = 20
IDLE_TIMEOUT_SECONDS = 300  # 5 min idle → close


def _get_decision_fn() -> Callable:
    for name in ("handle_query", "decide", "route_query", "run_decision"):
        fn = getattr(decision_mod, name, None)
        if callable(fn):
            return fn
    raise AttributeError("No decision function found in backend/core/decision.py")


async def _safe_send_json(ws: WebSocket, payload: dict, *, label: str) -> bool:
    if ws.application_state != WebSocketState.CONNECTED:
        logger.debug("skip_send label=%s (app_state)", label)
        return False
    if getattr(ws, "client_state", WebSocketState.CONNECTED) != WebSocketState.CONNECTED:
        logger.debug("skip_send label=%s (client_state)", label)
        return False
    try:
        await ws.send_json(payload)
        return True
    except (WebSocketDisconnect, RuntimeError, Exception) as exc:
        logger.warning("send_failed label=%s: %s", label, exc)
        return False


async def _safe_close(ws: WebSocket, code: int = 1000) -> None:
    try:
        if ws.application_state == WebSocketState.CONNECTED:
            await ws.close(code=code)
    except Exception:
        pass


def _extract_response_text(payload: dict) -> str:
    data = payload.get("data") or {}
    ranking = data.get("ranking") or {}
    return ranking.get("llm_response", "").strip() or payload.get("message", "")


def _extract_tts_text(payload: dict) -> str:
    """Extract voice-optimised TTS text, falling back to llm_response."""
    data = payload.get("data") or {}
    ranking = data.get("ranking") or {}
    return (ranking.get("tts_response") or "").strip() or _extract_response_text(payload)


def _extract_hotels(payload: dict) -> list:
    data = payload.get("data") or {}
    ranking = data.get("ranking") or {}
    return ranking.get("ranked_hotels") or data.get("results") or []


# ─────────────────────────────────────────────
#  TTS helper – streams audio to client
# ─────────────────────────────────────────────
async def _stream_tts(ws: WebSocket, text: str) -> None:
    """Generate and stream TTS audio chunks to client."""
    if not text:
        return
    
    # Skip TTS if no API key configured
    if not ELEVEN_API_KEY:
        logger.warning("tts_skipped: no ELEVEN_API_KEY configured")
        return
    
    await _safe_send_json(ws, {"type": "tts_start"}, label="tts_start")
    tts_success = False
    
    try:
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
        
        # DIAGNOSTIC: Collect all audio for debugging
        import base64
        all_audio_bytes = b''
        chunk_count = 0
        
        async for event in tts.stream_audio(text):
            msg_type = event.get("message_type")
            if msg_type == "audio":
                audio_b64 = event.get("audio", "")
                chunk_count += 1
                
                # Decode to check actual bytes
                try:
                    audio_bytes = base64.b64decode(audio_b64)
                    all_audio_bytes += audio_bytes
                    logger.info(f"TTS chunk {chunk_count}: {len(audio_b64)} b64 chars -> {len(audio_bytes)} bytes")
                except Exception as e:
                    logger.error(f"Failed to decode TTS chunk {chunk_count}: {e}")
                
                await _safe_send_json(ws, {"type": "tts_audio", "audio": audio_b64}, label="tts_chunk")
                tts_success = True
            elif msg_type == "flush":
                break
            elif msg_type == "error":
                error_msg = event.get("error", "Unknown TTS error")
                logger.error("tts_api_error: %s", error_msg)
                if "payment_required" in str(error_msg).lower():
                    logger.warning("ElevenLabs quota exhausted - TTS disabled for this turn")
                await _safe_send_json(ws, {"type": "tts_error", "error": error_msg}, label="tts_error")
                break
        
        # DIAGNOSTIC: Log total audio received and save to file
        if all_audio_bytes:
            logger.info(f"TTS TOTAL: {len(all_audio_bytes)} bytes from {chunk_count} chunks")
            logger.info(f"TTS byte length is {'EVEN' if len(all_audio_bytes) % 2 == 0 else 'ODD'}")
            
            # Save as WAV file for testing
            try:
                import wave
                wav_path = "debug_tts_output.wav"
                with wave.open(wav_path, "wb") as wav:
                    wav.setnchannels(1)  # Mono
                    wav.setsampwidth(2)  # 16-bit = 2 bytes
                    wav.setframerate(16000)  # 16kHz
                    wav.writeframes(all_audio_bytes)
                logger.info(f"Saved TTS audio to {wav_path} for testing")
            except Exception as e:
                logger.error(f"Failed to save WAV: {e}")
        
        if tts_success:
            logger.info("tts_completed")
        await _safe_send_json(ws, {"type": "tts_end"}, label="tts_end")
        
    except Exception as exc:
        logger.exception("tts_generation_failed")
        await _safe_send_json(ws, {"type": "tts_error", "error": str(exc)}, label="tts_exception")
        await _safe_send_json(ws, {"type": "tts_end"}, label="tts_end_after_error")


# ─────────────────────────────────────────────
#  Decision helper – calls decision engine and
#  sends assistant_response + TTS
# ─────────────────────────────────────────────
async def _run_decision_and_respond(
    ws: WebSocket,
    text: str,
    session_id: str,
    session_context: dict,
    *,
    force_mode: Optional[str] = None,
    preset_location: Optional[str] = None,
    preset_dates: Optional[dict] = None,
    rerank_hotels: Optional[list] = None,
) -> dict:
    """Call decision engine, send response + TTS.  Returns updated session_context."""
    t0 = time.monotonic()
    try:
        logger.info("calling_decision text=%r force_mode=%s", text, force_mode)
        decision_fn = _get_decision_fn()

        kwargs: Dict[str, Any] = {"mode": "voice", "context": session_context}
        if force_mode:
            kwargs["force_mode"] = force_mode
        if preset_location:
            kwargs["preset_location"] = preset_location
        if preset_dates:
            kwargs["preset_dates"] = preset_dates
        if rerank_hotels:
            kwargs["rerank_hotels"] = rerank_hotels

        result = decision_fn(text, **kwargs)
        if inspect.isawaitable(result):
            result = await result

        response_text = _extract_response_text(result)
        tts_text = _extract_tts_text(result)
        hotels = _extract_hotels(result)
        logger.info("decision_result action=%s response_len=%d tts_len=%d hotels=%d",
                    result.get("action", "?"), len(response_text), len(tts_text), len(hotels))

        # Fallback: if no TTS text but we have a response, use that
        if not tts_text and response_text:
            tts_text = response_text
        # Last resort: synthesize a message from the result
        if not tts_text:
            tts_text = result.get("message") or "I found some results for you."

        session_context = await save_session_turn(
            session_id=session_id,
            user_text=text,
            assistant_text=response_text,
            result_payload=result,
            existing_context=session_context,
        )

        elapsed = round(time.monotonic() - t0, 2)
        logger.info("decision_completed elapsed=%.2fs", elapsed)

        payload = {
            "type": "assistant_response",
            "result": jsonable_encoder({
                **result,
                "response": response_text,
                "hotels": hotels,
                "session_id": session_id,
                "conversation_id": session_context.get("conversation_id"),
            }),
            "meta": {"elapsed_s": elapsed},
        }
        sent = await _safe_send_json(ws, payload, label="assistant_response")
        if sent:
            await _stream_tts(ws, tts_text)

    except Exception as exc:
        logger.exception("decision_call_failed")
        await _safe_send_json(ws, {
            "type": "assistant_response",
            "result": {"action": "ERROR", "message": f"Decision layer failed: {exc}"},
        }, label="assistant_error")

    return session_context


# ─────────────────────────────────────────────
#  Voice turn: STT → Decision → TTS
# ─────────────────────────────────────────────
async def _run_voice_turn(
    ws: WebSocket,
    audio_q: "asyncio.Queue[Optional[bytes]]",
    session_id: str,
    session_context: dict,
    turn_meta: dict,
) -> dict:
    """Execute a single voice turn. Returns updated session_context."""

    async def audio_chunks() -> AsyncIterator[bytes]:
        while True:
            chunk = await audio_q.get()
            if chunk is None:
                break
            yield chunk

    latest_text = ""
    decision_done = False

    try:
        stt = ElevenLabsSTT(
            ElevenSTTConfig(
                api_key=ELEVEN_API_KEY,
                model_id=ELEVEN_STT_MODEL_ID,
                sample_rate=ELEVEN_STT_SAMPLE_RATE,
            )
        )

        stt_gen = _consume_stt(stt, audio_chunks())
        try:
            async with asyncio.timeout(STT_TIMEOUT_SECONDS):
                async for event in stt_gen:
                    msg_type = (event or {}).get("message_type")
                    logger.debug("stt_event type=%s text=%s", msg_type, (event or {}).get("text", "")[:80])

                    if msg_type == "partial_transcript":
                        latest_text = (event.get("text") or "").strip()
                        await _safe_send_json(ws, {"type": "partial_text", "text": latest_text}, label="partial_text")
                        continue

                    if msg_type in ("committed_transcript", "final_transcript"):
                        txt = (event.get("text") or "").strip()
                        if txt:
                            latest_text = txt
                        logger.info("stt_final text=%r (msg_type=%s)", latest_text, msg_type)
                        await _safe_send_json(ws, {"type": "final_text", "text": latest_text}, label="final_text")
                        break  # STT done – proceed to decision engine immediately

                    if msg_type == "session_started":
                        logger.debug("stt_session_started")
                        continue

                    # debug / unknown
                    logger.debug("stt_unknown_event: %s", event)
        finally:
            try:
                async with asyncio.timeout(5):
                    await stt_gen.aclose()
            except (asyncio.TimeoutError, Exception):
                logger.warning("stt_gen_aclose failed or timed out")

    except asyncio.TimeoutError:
        logger.warning("stt_timeout after %ds – using partial text: %r", STT_TIMEOUT_SECONDS, latest_text)
        await _safe_send_json(ws, {"type": "error", "code": "stt_timeout", "message": "Speech recognition timed out. Please try again."}, label="stt_timeout")
    except Exception as exc:
        logger.exception("stt_stream_error")
        await _safe_send_json(ws, {"type": "error", "code": "stt_error", "message": str(exc)}, label="stt_error")

    final_text = latest_text.strip()
    if not final_text:
        await _safe_send_json(ws, {"type": "error", "code": "no_transcript", "message": "No speech detected. Please try again."}, label="no_transcript")
        await _safe_send_json(ws, {"type": "turn_end"}, label="turn_end_empty")
        return session_context

    logger.info("stt_done, starting decision for: %r", final_text)
    await _safe_send_json(ws, {"type": "processing"}, label="processing")

    session_context = await _run_decision_and_respond(
        ws, final_text, session_id, session_context,
        force_mode=turn_meta.get("force_mode"),
        preset_location=turn_meta.get("preset_location"),
        preset_dates=turn_meta.get("preset_dates"),
        rerank_hotels=turn_meta.get("rerank_hotels"),
    )

    await _safe_send_json(ws, {"type": "turn_end"}, label="turn_end")
    return session_context


async def _consume_stt(stt: ElevenLabsSTT, chunks: AsyncIterator[bytes]):
    """Wrapper so we can pass this to asyncio.wait_for."""
    async for event in stt.stream_transcripts(chunks):
        yield event


# ═════════════════════════════════════════════
#  Main WebSocket endpoint – persistent multi-turn
# ═════════════════════════════════════════════
@router.websocket("/stream")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()
    session_id = (websocket.query_params.get("session_id") or "").strip() or str(uuid4())
    session_context = await get_session_context(session_id)
    logger.info("voice_ws_connected session_id=%s", session_id)

    if not ELEVEN_API_KEY:
        await _safe_send_json(websocket, {"type": "error", "code": "missing_api_key", "message": "ELEVEN_API_KEY not configured"}, label="missing_key")
        await _safe_close(websocket)
        return

    # Notify client the connection is ready
    await _safe_send_json(websocket, {"type": "ready", "session_id": session_id}, label="ready")

    # Mutable shared state so background tasks can update session_context
    state: Dict[str, Any] = {"session_context": session_context}

    turn_meta: dict = {}
    audio_q: Optional[asyncio.Queue] = None
    active_task: Optional[asyncio.Task] = None

    # ── Background wrappers ──
    async def _bg_voice_turn(ws, aq, sid, meta):
        """Run voice turn as a background task so the receive-loop stays responsive."""
        try:
            new_ctx = await _run_voice_turn(ws, aq, sid, state["session_context"], meta)
            state["session_context"] = new_ctx
        except asyncio.CancelledError:
            logger.info("bg_voice_turn cancelled (client disconnected)")
            raise  # re-raise for proper task cancellation
        except Exception as exc:
            logger.exception("bg_voice_turn_error: %s", exc)
            await _safe_send_json(ws, {"type": "turn_end"}, label="turn_end_after_error")

    async def _bg_form_search(ws, msg, sid):
        """Run form search as a background task."""
        try:
            query = (msg.get("query") or "").strip() or "Show me hotels"
            await _safe_send_json(ws, {"type": "processing"}, label="form_processing")
            new_ctx = await _run_decision_and_respond(
                ws, query, sid, state["session_context"],
                force_mode=msg.get("force_mode"),
                preset_location=msg.get("preset_location"),
                preset_dates=msg.get("preset_dates"),
                rerank_hotels=msg.get("rerank_hotels"),
            )
            state["session_context"] = new_ctx
            await _safe_send_json(ws, {"type": "turn_end"}, label="form_turn_end")
        except asyncio.CancelledError:
            logger.info("bg_form_search cancelled (client disconnected)")
            raise
        except Exception as exc:
            logger.exception("bg_form_search_error: %s", exc)
            await _safe_send_json(ws, {"type": "turn_end"}, label="turn_end_after_error")

    try:
        while True:
            try:
                raw_msg = await asyncio.wait_for(
                    websocket.receive(),
                    timeout=IDLE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.info("voice_ws_idle_timeout session_id=%s", session_id)
                await _safe_send_json(websocket, {"type": "error", "code": "idle_timeout", "message": "Connection timed out due to inactivity."}, label="idle_timeout")
                break

            # ── Disconnect ──
            if raw_msg.get("type") == "websocket.disconnect":
                logger.info("client_disconnected session_id=%s", session_id)
                break

            # ── Binary audio data ──
            if raw_msg.get("bytes") is not None:
                chunk = raw_msg["bytes"]
                if audio_q is not None and chunk:
                    await audio_q.put(chunk)
                continue

            # ── Text/JSON messages ──
            text_data = raw_msg.get("text")
            if text_data is None:
                continue

            try:
                msg = json.loads(text_data)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            # -- Ping/pong for keepalive --
            if msg_type == "ping":
                await _safe_send_json(websocket, {"type": "pong"}, label="pong")
                continue

            # -- Turn start: client is about to stream audio --
            if msg_type == "turn_start":
                turn_meta = {
                    "force_mode": msg.get("force_mode"),
                    "preset_location": msg.get("preset_location"),
                    "preset_dates": msg.get("preset_dates"),
                    "rerank_hotels": msg.get("rerank_hotels"),
                }
                audio_q = asyncio.Queue()
                await _safe_send_json(websocket, {"type": "turn_ready"}, label="turn_ready")
                continue

            # -- Audio end: finish this voice turn --
            if msg_type == "audio_end":
                logger.info("recv_audio_end session_id=%s has_queue=%s", session_id, audio_q is not None)
                if audio_q is not None:
                    await audio_q.put(None)  # signal end of audio
                    # Run voice turn as background task so the main loop
                    # keeps reading pings / detecting client disconnect.
                    active_task = asyncio.create_task(
                        _bg_voice_turn(websocket, audio_q, session_id, turn_meta)
                    )
                    audio_q = None
                    turn_meta = {}
                else:
                    await _safe_send_json(websocket, {"type": "error", "code": "no_turn", "message": "No active voice turn."}, label="no_turn")
                continue

            # -- Form search: decision without audio (live prices initial search) --
            if msg_type == "form_search":
                active_task = asyncio.create_task(
                    _bg_form_search(websocket, msg, session_id)
                )
                continue

    except WebSocketDisconnect:
        logger.info("voice_ws_disconnected session_id=%s", session_id)
    except Exception as exc:
        logger.exception("voice_ws_error")
        await _safe_send_json(websocket, {"type": "error", "code": "internal", "message": f"Server error: {exc}"}, label="ws_error")
    finally:
        # Cancel any in-flight processing task
        if active_task and not active_task.done():
            active_task.cancel()
            with suppress(asyncio.CancelledError):
                await active_task
        # Clean up any in-flight audio queue
        if audio_q is not None:
            await audio_q.put(None)
        await _safe_close(websocket)
        logger.info("voice_ws_finished session_id=%s", session_id)