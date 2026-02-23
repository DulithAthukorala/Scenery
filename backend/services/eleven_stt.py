# backend/services/eleven_stt.py
from __future__ import annotations

import base64 # convert audio to bas64 for ElevenLabs
import json # WebSocket messages are sent as JSON text.
from dataclasses import dataclass
from typing import AsyncIterator, Dict, Any, Optional

import websockets # helps to talk to ElevenLabs real-time


@dataclass(frozen=True) # frozen=True makes it unchangeable
class ElevenSTTConfig:
    api_key: str
    model_id: str = "scribe_v2_realtime"
    sample_rate: int = 16000 # 16000 Hz is standard for speech recognition (ElevenLabs docs)


class ElevenLabsSTT:
    """
    Protocol (docs):
    - Send: {"message_type":"input_audio_chunk","audio_base_64":"...","commit":true,"sample_rate":16000}
    - Receive: message_type in {"partial_transcript","committed_transcript",...}
    """
    WS_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"

    def __init__(self, cfg: ElevenSTTConfig):
        """
        ex:
            cfg = ElevenSTTConfig(api_key="mykey")
            stt = ElevenLabsSTT(cfg)
        """
        self.cfg = cfg

    async def stream_transcripts(
        self,
        audio_chunks: AsyncIterator[bytes], # 20-50ms raw audio chunks
        *,
        previous_text: Optional[str] = None, # helps for long conversations (context for better accuracy)
        commit_each_chunk: bool = False, # tells user finished speaking and should finalize the transcript
    ) -> AsyncIterator[Dict[str, Any]]:
        # wss://api.elevenlabs.io/v1/speech-to-text/realtime?model_id=scribe_v2_realtime
        url = f"{self.WS_URL}?model_id={self.cfg.model_id}"
        headers = {"xi-api-key": self.cfg.api_key} # authentication for ElevenLabs API

        # connect to ElevenLabs
        async with websockets.connect(url, additional_headers=headers) as ws:
            # First message -> usually session_started
            first = await ws.recv() # wait for the first message
            yield json.loads(first) # {"message_type": "session_started"}

            async def sender():
                async for chunk in audio_chunks:
                    msg = {
                        "message_type": "input_audio_chunk",
                        "audio_base_64": base64.b64encode(chunk).decode("ascii"), # actual sound data converted to base64 string
                        "sample_rate": self.cfg.sample_rate,
                    }
                    # if you have previous text
                    if previous_text:
                        msg["previous_text"] = previous_text

                    # placed to false, and then true once speaking is done
                    if commit_each_chunk:
                        msg["commit"] = True

                    await ws.send(json.dumps(msg))

                # Final commit (when user stops speaking)
                await ws.send(json.dumps({"message_type": "input_audio_chunk", "audio_base_64": "", "commit": True}))


            # keeps receiving messages from ElevenLabs as txt
            async def receiver():
                while True:
                    raw = await ws.recv()
                    yield json.loads(raw)


            # running both sender() and receiver() concurrently
            send_task = None
            try:
                send_task = __import__("asyncio").create_task(sender())
                async for event in receiver():
                    yield event
            # if 
            finally:
                if send_task:
                    send_task.cancel()