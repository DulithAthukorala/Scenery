"""
ElevenLabs real-time speech-to-text streaming service.
"""
from __future__ import annotations

import base64 # convert audio to bas64 for ElevenLabs
import json # WebSocket messages are sent as JSON text.
from dataclasses import dataclass
from typing import AsyncIterator, Dict, Any, Optional

import websockets # helps to talk to ElevenLabs real-time
from websockets.exceptions import ConnectionClosedOK, ConnectionClosed # intentional closing and unintentional closing of erros

import asyncio


@dataclass(frozen=True) # frozen=True makes it unchangeable
class ElevenSTTConfig:
    api_key: str
    model_id: str = "scribe_v2_realtime"
    sample_rate: int = 16000 # 16000 Hz is standard for speech recognition (ElevenLabs docs)


class ElevenLabsSTT:
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
        
        url = f"{self.WS_URL}?model_id={self.cfg.model_id}"
        headers = {"xi-api-key": self.cfg.api_key} # authentication for ElevenLabs API

        # connect to ElevenLabs
        async with websockets.connect(url, additional_headers=headers) as ws:
            # First message -> usually session_started
            first = await ws.recv() # wait for the first message
            yield json.loads(first) # {"message_type": "session_started"}

            # sender() takes raw audio chunks, converts to base64, and sends to ElevenLabs
            async def sender():
                async for chunk in audio_chunks:
                    msg = {
                        "message_type": "input_audio_chunk",
                        "audio_base_64": base64.b64encode(chunk).decode("ascii"), # audio bytes (binary) -> base64-encoded bytes -> ASCII for safe JSON/WebSocket transport
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
                try:
                    await ws.send(json.dumps({"message_type": "input_audio_chunk", "audio_base_64": "", "commit": True}))
                except ConnectionClosed:
                    return


            # keeps receiving messages from ElevenLabs as txt
            async def receiver():
                while True:
                    try:
                        raw = await ws.recv()
                    except ConnectionClosedOK:
                        break
                    except ConnectionClosed:
                        break
                    yield json.loads(raw)


            # running both sender() and receiver() concurrently
            send_task = None
            try:
                send_task = asyncio.create_task(sender())
                async for event in receiver():
                    yield event
            # finnally runs when either sender() or receiver() finishes (like user stops speaking or connection closes) 
            finally:
                if send_task:
                    send_task.cancel() # if sender() is still running, stop it
                    try:
                        await send_task # wait for sender() to finish cleanup
                    except asyncio.CancelledError: # if there is a error during cancellation, ignore it
                        pass