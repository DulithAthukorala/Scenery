"""
Pipecat bot runner.

Exposes a tiny FastAPI server on port 8100 so the main FastAPI (Windows)
can trigger a bot for each voice session via POST /start.

The Pipecat pipeline runs in a Docker Linux container because daily-python
has no Windows wheels.

Pipeline:
    DailyTransport.input()
        → ElevenLabsSTTService   (speech-to-text)
        → HotelQueryProcessor    (decision engine + hotel card side-channel)
        → ElevenLabsTTSService   (text-to-speech)
        → DailyTransport.output()
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import aiohttp

# Make backend modules importable when run as `python -m backend.bot.pipecat_bot`
# inside the Docker container where the project root is mounted at /app.
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.elevenlabs.stt import ElevenLabsSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

from backend.bot.hotel_processor import HotelQueryProcessor
from backend.config import (
    DAILY_API_KEY,
    ELEVEN_API_KEY,
    ELEVEN_TTS_MODEL_ID,
    ELEVEN_TTS_VOICE_ID,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  FastAPI bot runner server
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Scenery Pipecat Bot Runner")


class StartBotRequest(BaseModel):
    room_url: str
    session_id: str
    bot_token: str = ""  # owner meeting token for the bot


@app.post("/start")
async def start_bot(payload: StartBotRequest):
    """Launch a Pipecat pipeline for this room in a background task."""
    asyncio.create_task(
        _run_bot(payload.room_url, payload.session_id, payload.bot_token)
    )
    return {"status": "starting", "session_id": payload.session_id}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
#  Pipecat pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def _run_bot(room_url: str, session_id: str, bot_token: str) -> None:
    logger.info("bot_starting room_url=%s session=%s", room_url, session_id)

    async with aiohttp.ClientSession() as aiohttp_session:
        await _run_bot_session(room_url, session_id, bot_token, aiohttp_session)


async def _run_bot_session(
    room_url: str, session_id: str, bot_token: str, aiohttp_session: aiohttp.ClientSession
) -> None:
    transport = DailyTransport(
        room_url=room_url,
        token=bot_token or None,
        bot_name="Scenery",
        params=DailyParams(
            api_key=DAILY_API_KEY,
            audio_in_enabled=True,
            audio_out_enabled=True,
            camera_out_enabled=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            transcription_enabled=False,  # we use ElevenLabs STT instead
        ),
    )

    stt = ElevenLabsSTTService(
        api_key=ELEVEN_API_KEY,
        model_id="scribe_v1",
        language="en",
        aiohttp_session=aiohttp_session,
    )

    hotel_processor = HotelQueryProcessor(
        session_id=session_id,
    )

    tts = ElevenLabsTTSService(
        api_key=ELEVEN_API_KEY,
        voice_id=ELEVEN_TTS_VOICE_ID,
        model_id=ELEVEN_TTS_MODEL_ID,
        output_format="pcm_16000",
    )

    pipeline = Pipeline([
        transport.input(),
        stt,
        hotel_processor,
        tts,
        transport.output(),
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
    )

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        participant_id = participant.get("id") or participant.get("session_id", "")
        logger.info("first_participant_joined id=%s", participant_id)
        # Enable STT transcription for this participant
        try:
            await transport.capture_participant_transcription(participant_id)
        except Exception as exc:
            logger.warning("capture_participant_transcription failed: %s", exc)

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        logger.info("participant_left id=%s reason=%s", participant.get("id"), reason)
        await task.queue_frame(EndFrame())

    runner = PipelineRunner()
    try:
        await runner.run(task)
    except Exception:
        logger.exception("bot_error session=%s", session_id)
    finally:
        logger.info("bot_finished session=%s", session_id)


# ─────────────────────────────────────────────────────────────────────────────
#  Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8100, log_level="info")
