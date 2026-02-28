"""
ElevenLabs text-to-speech streaming service.
"""
from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import AsyncIterator, Dict, Any, Optional
from urllib.parse import urlencode

import certifi
import websockets
from websockets.exceptions import ConnectionClosedOK, ConnectionClosed

import asyncio


@dataclass(frozen=True)
class ElevenTTSConfig:
    api_key: str
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel voice (default)
    model_id: str = "eleven_turbo_v2_5"
    stability: float = 0.5
    similarity_boost: float = 0.75
    optimize_streaming_latency: int = 4  # 0-4, higher = lower latency but potentially lower quality
    output_format: str = "pcm_16000"  # 16kHz PCM audio

    def __post_init__(self) -> None:
        if not 0 <= self.stability <= 1:
            raise ValueError("stability must be between 0 and 1")
        if not 0 <= self.similarity_boost <= 1:
            raise ValueError("similarity_boost must be between 0 and 1")
        if not 0 <= self.optimize_streaming_latency <= 4:
            raise ValueError("optimize_streaming_latency must be between 0 and 4")


class ElevenLabsTTS:
    WS_URL = "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"

    def __init__(self, cfg: ElevenTTSConfig):
        """
        ex:
            cfg = ElevenTTSConfig(api_key="mykey", voice_id="21m00Tcm4TlvDq8ikWAM")
            tts = ElevenLabsTTS(cfg)
        """
        self.cfg = cfg

    async def stream_audio(
        self,
        text: str,
        *,
        enable_ssml_parsing: bool = False,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Streams audio chunks from ElevenLabs TTS service.
        
        Args:
            text: The text to convert to speech
            enable_ssml_parsing: Whether to parse SSML tags in the text
            
        Yields:
            Dict with message_type and data. Types include:
            - "session_started": Initial connection message
            - "audio": Contains audio chunk in "audio" field (base64 encoded)
            - "flush": End of audio stream
            - "error": Error message
        """
        url = self.WS_URL.format(voice_id=self.cfg.voice_id)
        query = urlencode({
            "model_id": self.cfg.model_id,
            "output_format": self.cfg.output_format,
            "optimize_streaming_latency": str(self.cfg.optimize_streaming_latency),
        })
        url = f"{url}?{query}"
        
        headers = {"xi-api-key": self.cfg.api_key}
        
        # Create SSL context with certifi certificates
        ssl_context = ssl.create_default_context(cafile=certifi.where())

        async with websockets.connect(url, additional_headers=headers, ssl=ssl_context) as ws:
            # Send initial configuration
            config_msg = {
                "text": " ",  # Start with a space to initialize the stream
                "voice_settings": {
                    "stability": self.cfg.stability,
                    "similarity_boost": self.cfg.similarity_boost,
                },
                "xi_api_key": self.cfg.api_key,
                "enable_ssml_parsing": enable_ssml_parsing,
            }
            await ws.send(json.dumps(config_msg))

            # Send the actual text
            text_msg = {
                "text": text,
                "try_trigger_generation": True,
            }
            await ws.send(json.dumps(text_msg))

            # Send end-of-stream marker
            eos_msg = {"text": ""}
            await ws.send(json.dumps(eos_msg))

            # Receive audio chunks
            while True:
                try:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    
                    # Check for different message types
                    if "audio" in data:
                        yield {"message_type": "audio", "audio": data["audio"]}
                    elif "isFinal" in data and data["isFinal"]:
                        yield {"message_type": "flush"}
                        break
                    elif "error" in data:
                        yield {"message_type": "error", "error": data["error"]}
                        break
                    else:
                        # Other messages (like alignment info, etc.)
                        yield {"message_type": "metadata", "data": data}
                        
                except ConnectionClosedOK:
                    break
                except ConnectionClosed:
                    break
                except json.JSONDecodeError:
                    # Handle binary audio data (if any)
                    continue

    async def synthesize_to_bytes(self, text: str) -> bytes:
        """
        Convenience method to get all audio as a single bytes object.
        Collects all audio chunks and returns them concatenated.
        """
        import base64
        audio_chunks = []
        
        async for event in self.stream_audio(text):
            if event.get("message_type") == "audio":
                audio_b64 = event.get("audio", "")
                if audio_b64:
                    audio_bytes = base64.b64decode(audio_b64)
                    audio_chunks.append(audio_bytes)
        
        return b"".join(audio_chunks)
