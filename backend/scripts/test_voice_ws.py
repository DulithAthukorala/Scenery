import time
import wave
import json
import os
import websocket

WS_URL = os.getenv("WS_URL", "ws://localhost:8000/voice/stream")

# 100ms chunk at 16kHz, 16-bit mono:
# 16000 samples/sec * 0.1 sec = 1600 samples
# 1600 samples * 2 bytes/sample = 3200 bytes
CHUNK_BYTES = 3200


def main():
    ws = websocket.create_connection(WS_URL, timeout=10)
    ws.settimeout(15)
    print("Connected:", WS_URL)

    wav_path = os.getenv("WAV_PATH", "backend/scripts/test_pcm.wav")
    wf = wave.open(wav_path, "rb") # Make sure there is a 16kHz mono PCM16 WAV at this path for testing
    print("Channels:", wf.getnchannels())
    print("Sample rate:", wf.getframerate())
    print("Sample width:", wf.getsampwidth())

    # Basic sanity checks for our STT pipeline format
    if wf.getnchannels() != 1 or wf.getframerate() != 16000 or wf.getsampwidth() != 2:
        print("WARNING: WAV is not 16kHz mono PCM16. Convert to 16kHz mono PCM16 for best results.")

    # Send audio frames
    while True:
        data = wf.readframes(CHUNK_BYTES // 2)  # //2 because readframes takes samples, not bytes (PCM16 mono)
        if not data:
            break
        ws.send(data, opcode=websocket.ABNF.OPCODE_BINARY)
        time.sleep(0.1)

    print("Finished sending audio")

    # ✅ END-OF-AUDIO marker (server will stop receiver on b"")
    ws.send(b"", opcode=websocket.ABNF.OPCODE_BINARY)

    got_assistant = False
    start_wait = time.time()

    # Read server events until assistant_response or timeout
    try:
        while True:
            if time.time() - start_wait > 20:
                print("Timed out waiting for assistant_response")
                break

            msg = ws.recv()
            try:
                payload = json.loads(msg)
            except Exception:
                print("Server replied (raw):", msg)
                continue

            print("Server replied:", payload)

            msg_type = payload.get("type")
            if msg_type == "assistant_response":
                got_assistant = True
                break
            if msg_type == "error":
                break

    except websocket.WebSocketTimeoutException:
        print("Socket timeout waiting for server messages.")
    except Exception as exc:
        print("Server closed connection:", repr(exc))
    finally:
        ws.close()

    print("assistant_response_received:", got_assistant)


if __name__ == "__main__":
    main()