"""
Pipecat bot runner.

Exposes a tiny FastAPI server on port 8100 so the main FastAPI (Windows)
can trigger a bot for each voice session via POST /start.

The Pipecat pipeline runs in a Docker Linux container because daily-python
has no Windows wheels.

Pipeline:
    DailyTransport.input()
        → ElevenLabsRealtimeSTTService  (speech-to-text, WebSocket streaming)
        → HotelQueryProcessor           (decision engine + hotel card side-channel)
        → ElevenLabsTTSService          (text-to-speech)
        → DailyTransport.output()
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

# Make backend modules importable when run as `python -m backend.bot.pipecat_bot`
# inside the Docker container where the project root is mounted at /app.
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from pipecat.frames.frames import EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.elevenlabs.stt import CommitStrategy, ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.tts_service import TextAggregationMode
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
    await _run_bot_session(room_url, session_id, bot_token)


async def _run_bot_session(
    room_url: str, session_id: str, bot_token: str
) -> None:
    transport = DailyTransport(
        room_url=room_url,
        token=bot_token or None,
        bot_name="Scenery",
        params=DailyParams(
            api_key=DAILY_API_KEY,
            audio_in_enabled=True,
            audio_in_sample_rate=24000,
            audio_out_enabled=True,
            audio_out_sample_rate=24000,
            camera_out_enabled=False,
            transcription_enabled=False,  # we use ElevenLabs STT instead
        ),
    )

    stt = ElevenLabsRealtimeSTTService(
        api_key=ELEVEN_API_KEY,
        commit_strategy=CommitStrategy.VAD,
        settings=ElevenLabsRealtimeSTTService.Settings(model="scribe_v2_realtime"),
    )

    hotel_processor = HotelQueryProcessor(
        session_id=session_id,
    )

    tts = ElevenLabsTTSService(
        api_key=ELEVEN_API_KEY,
        sample_rate=24000,
        # TOKEN mode sends the full text to ElevenLabs as one chunk
        # instead of splitting into sentences (which causes half-response issues).
        text_aggregation_mode=TextAggregationMode.TOKEN,
        settings=ElevenLabsTTSService.Settings(
            voice=ELEVEN_TTS_VOICE_ID,
            model="eleven_multilingual_v2",
            stability=0.4,
            similarity_boost=0.8,
            speed=0.95,
        ),
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
        params=PipelineParams(
            allow_interruptions=False,
            audio_in_sample_rate=24000,
            audio_out_sample_rate=24000,
        ),
    )

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        participant_id = participant.get("id") or participant.get("session_id", "")
        logger.info("first_participant_joined id=%s", participant_id)
        # ElevenLabsRealtimeSTTService processes audio directly from the pipeline;
        # capture_participant_transcription is for Daily's built-in STT and must NOT be called here.

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
