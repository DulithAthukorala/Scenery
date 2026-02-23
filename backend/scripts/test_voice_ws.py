import os
import time
import websocket  # from websocket-client

WS_URL = os.getenv("WS_URL", "ws://localhost:8000/voice/stream")

def main():
    ws = websocket.create_connection(WS_URL)
    print("Connected:", WS_URL)

    # send a few fake "audio" chunks (just bytes) to test server receive/send
    for i in range(5):
        fake_chunk = b"\x00" * (200 + i * 50)  # 200, 250, 300...
        ws.send(fake_chunk, opcode=websocket.ABNF.OPCODE_BINARY)

        msg = ws.recv()
        print("Server replied:", msg)

        time.sleep(0.2)

    ws.close()
    print("Closed.")

if __name__ == "__main__":
    main()