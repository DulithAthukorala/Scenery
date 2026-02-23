import asyncio
import json
import os
import wave

import websockets

WS_URL = os.getenv("WS_URL", "ws://localhost:8000/voice/stream")
CHUNK_BYTES = 3200


async def run_test(wav_path: str | None = None):
    wav_path = wav_path or os.getenv("WAV_PATH", "backend/scripts/test_pcm.wav")
    async with websockets.connect(WS_URL, max_size=2**22) as ws:
        print("Connected:", WS_URL)

        with wave.open(wav_path, "rb") as wf:
            print("Channels:", wf.getnchannels())
            print("Sample rate:", wf.getframerate())
            print("Sample width:", wf.getsampwidth())

            if wf.getnchannels() != 1 or wf.getframerate() != 16000 or wf.getsampwidth() != 2:
                print("WARNING: WAV is not 16kHz mono PCM16")

            while True:
                data = wf.readframes(CHUNK_BYTES // 2)
                if not data:
                    break
                await ws.send(data)
                await asyncio.sleep(0.1)

        await ws.send(b"")
        print("Finished sending audio + EOF marker")

        got_assistant = False
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=20)
                payload = json.loads(raw)
                print("Server replied:", payload)

                msg_type = payload.get("type")
                if msg_type == "assistant_response":
                    got_assistant = True
                    break
                if msg_type == "error":
                    break
        except asyncio.TimeoutError:
            print("Timed out waiting for assistant_response")

        print("assistant_response_received:", got_assistant)


if __name__ == "__main__":
    asyncio.run(run_test())
