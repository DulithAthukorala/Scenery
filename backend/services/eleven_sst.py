# backend/services/eleven_stt.py
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import AsyncIterator, Dict, Any, Optional

import websockets


@dataclass(frozen=True)
class ElevenSTTConfig:
    api_key: str
    model_id: str = "scribe_v2_realtime"
    sample_rate: int = 16000


class ElevenLabsSTT:
    """
    Protocol (docs):
    - Send: {"message_type":"input_audio_chunk","audio_base_64":"...","commit":true,"sample_rate":16000}
    - Receive: message_type in {"partial_transcript","committed_transcript",...}
    """
    WS_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"

    def __init__(self, cfg: ElevenSTTConfig):
        self.cfg = cfg

    async def stream_transcripts(
        self,
        audio_chunks: AsyncIterator[bytes],
        *,
        previous_text: Optional[str] = None,
        commit_each_chunk: bool = False,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        audio_chunks: async iterator yielding raw audio bytes (we'll base64 them).
        Yields: transcript events from ElevenLabs as dicts.
        """
        url = f"{self.WS_URL}?model_id={self.cfg.model_id}"
        headers = {"xi-api-key": self.cfg.api_key}

        async with websockets.connect(url, extra_headers=headers) as ws:
            # First message from server is usually session_started (we yield it)
            first = await ws.recv()
            yield json.loads(first)

            async def sender():
                async for chunk in audio_chunks:
                    msg = {
                        "message_type": "input_audio_chunk",
                        "audio_base_64": base64.b64encode(chunk).decode("ascii"),
                        "sample_rate": self.cfg.sample_rate,
                    }
                    if previous_text:
                        msg["previous_text"] = previous_text
                    # If True: every chunk is treated like an utterance boundary (usually you want False)
                    if commit_each_chunk:
                        msg["commit"] = True

                    await ws.send(json.dumps(msg))

                # Final commit to flush last partial -> committed transcript
                await ws.send(json.dumps({"message_type": "input_audio_chunk", "audio_base_64": "", "commit": True}))

            async def receiver():
                while True:
                    raw = await ws.recv()
                    yield json.loads(raw)

            # Run sender while we keep yielding receiver events
            send_task = None
            try:
                send_task = __import__("asyncio").create_task(sender())
                async for event in receiver():
                    yield event
            finally:
                if send_task:
                    send_task.cancel()