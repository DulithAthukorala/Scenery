from __future__ import annotations

import json
import logging
from typing import Optional

from pipecat.frames.frames import Frame, TranscriptionFrame, TextFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.transports.daily.transport import DailyOutputTransportMessageFrame

from backend.core.decision import handle_query
from backend.services.conversation_memory import get_session_context, save_session_turn

logger = logging.getLogger(__name__)


def _extract_tts_text(result: dict) -> str:
    ranking = (result.get("data") or {}).get("ranking") or {}
    tts = (ranking.get("tts_response") or "").strip()
    if tts:
        return tts
    llm = (ranking.get("llm_response") or "").strip()
    if llm:
        return llm
    return (result.get("message") or "I found some results for you.").strip()


def _extract_display_text(result: dict) -> str:
    ranking = (result.get("data") or {}).get("ranking") or {}
    llm = (ranking.get("llm_response") or "").strip()
    return llm or _extract_tts_text(result)


def _extract_hotels(result: dict) -> list:
    ranking = (result.get("data") or {}).get("ranking") or {}
    hotels = ranking.get("ranked_hotels") or (result.get("data") or {}).get("results") or []
    return hotels if isinstance(hotels, list) else []


class HotelQueryProcessor(FrameProcessor):
    """
    Bridges Pipecat's STT output to the Scenery decision engine.
    Receives TranscriptionFrame → runs handle_query() → emits TextFrame for TTS.
    Sends hotel card data to the browser via Daily app messages.
    """

    def __init__(self, session_id: str, **kwargs):
        super().__init__(**kwargs)
        self._session_id = session_id
        self._session_context: Optional[dict] = None

    async def _send_app_message(self, msg: dict) -> None:
        """Push a Daily app message downstream — picked up by DailyOutputTransport."""
        frame = DailyOutputTransportMessageFrame(message=json.dumps(msg))
        await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if not isinstance(frame, TranscriptionFrame):
            await self.push_frame(frame, direction)
            return

        user_text = (frame.text or "").strip()
        if not user_text:
            await self.push_frame(frame, direction)
            return

        logger.info("hotel_processor text=%r session=%s", user_text, self._session_id)

        # Tell the browser the transcript is final and processing has begun
        await self._send_app_message({"type": "final_text", "text": user_text})
        await self._send_app_message({"type": "processing"})

        try:
            if self._session_context is None:
                self._session_context = await get_session_context(self._session_id)

            result = await handle_query(
                user_text,
                mode="voice",
                context=self._session_context,
            )

            tts_text = _extract_tts_text(result)
            display_text = _extract_display_text(result)
            hotels = _extract_hotels(result)

            # Persist conversation turn
            self._session_context = await save_session_turn(
                session_id=self._session_id,
                user_text=user_text,
                assistant_text=display_text,
                result_payload=result,
                existing_context=self._session_context,
            )

            # Send hotel cards + text to browser via Daily app message
            await self._send_app_message({
                "type": "assistant_response",
                "result": {
                    "response": display_text,
                    "hotels": hotels,
                    "action": result.get("action"),
                    "session_id": self._session_id,
                },
            })

            # Drive TTS downstream
            await self.push_frame(TextFrame(text=tts_text), direction)

        except Exception:
            logger.exception("hotel_processor_error session=%s", self._session_id)
            await self._send_app_message({
                "type": "assistant_response",
                "result": {
                    "response": "Sorry, I had trouble processing that request.",
                    "hotels": [],
                    "session_id": self._session_id,
                },
            })
            await self.push_frame(
                TextFrame(text="Sorry, I had trouble processing that request."),
                direction,
            )
