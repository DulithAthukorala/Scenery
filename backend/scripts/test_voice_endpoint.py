"""
Test script for voice WebSocket endpoint with LLM ranking.
Sends audio, receives transcription, and displays assistant response with voice-mode tone.
"""
import asyncio
import json
import os
import wave
from pathlib import Path

import websockets

WS_URL = os.getenv("WS_URL", "ws://localhost:8000/voice/stream")
CHUNK_BYTES = 3200


def print_section(title: str):
    """Pretty print section headers."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


async def test_voice_stream(wav_path: str | None = None):
    """
    Test the voice WebSocket endpoint:
    1. Connect to WebSocket
    2. Send audio chunks
    3. Receive STT events
    4. Get assistant response with LLM ranking
    """
    wav_path = wav_path or os.getenv("WAV_PATH", "backend/scripts/test_pcm.wav")
    
    if not Path(wav_path).exists():
        print(f"❌ WAV file not found: {wav_path}")
        return
    
    print_section("VOICE ENDPOINT TEST")
    print(f"WebSocket URL: {WS_URL}")
    print(f"Audio file: {wav_path}")
    
    try:
        async with websockets.connect(WS_URL, max_size=2**22) as ws:
            print("✅ Connected to voice stream")
            
            # Read and send audio
            print_section("SENDING AUDIO")
            with wave.open(wav_path, "rb") as wf:
                print(f"  Channels: {wf.getnchannels()}")
                print(f"  Sample rate: {wf.getframerate()} Hz")
                print(f"  Sample width: {wf.getsampwidth()} bytes")
                print(f"  Duration: {wf.getnframes() / wf.getframerate():.2f} seconds")
                
                if wf.getnchannels() != 1 or wf.getframerate() != 16000 or wf.getsampwidth() != 2:
                    print("  ⚠️  WAV is not 16kHz mono PCM16 (may not work correctly)")
                
                chunk_count = 0
                while True:
                    data = wf.readframes(CHUNK_BYTES // 2)
                    if not data:
                        break
                    await ws.send(data)
                    chunk_count += 1
                    await asyncio.sleep(0.05)  # Simulate real-time streaming
                
                print(f"  Sent {chunk_count} audio chunks")
            
            # Send EOF marker
            await ws.send(b"")
            print("  ✅ Sent EOF marker")
            
            # Receive responses
            print_section("RECEIVING RESPONSES")
            
            partial_texts = []
            final_text = None
            assistant_response = None
            other_events = []
            
            try:
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    payload = json.loads(raw)
                    msg_type = payload.get("type")
                    
                    if msg_type == "partial_text":
                        text = payload.get("text", "")
                        partial_texts.append(text)
                        print(f"  📝 Partial: {text}")
                    
                    elif msg_type == "final_text":
                        final_text = payload.get("text", "")
                        print(f"  ✅ Final: {final_text}")
                    
                    elif msg_type == "assistant_response":
                        assistant_response = payload
                        print(f"  🤖 Assistant response received!")
                        break
                    
                    elif msg_type == "error":
                        print(f"  ❌ Error: {payload.get('message')}")
                        break
                    
                    elif msg_type == "stt_event":
                        event = payload.get("event", {})
                        event_type = event.get("message_type")
                        if event_type == "session_started":
                            config = event.get("config", {})
                            print(f"  🎤 Session started - Language: {config.get('language_code', 'unknown')}")
                        else:
                            other_events.append(event)
                    
                    elif msg_type == "server_debug":
                        print(f"  🔧 Debug: {payload.get('message')}")
                    
                    else:
                        other_events.append(payload)
            
            except asyncio.TimeoutError:
                print("  ⏱️  Timeout waiting for response")
            
            # Display results
            print_section("TEST RESULTS")
            
            print(f"\n📊 Transcript Summary:")
            print(f"  Partial updates: {len(partial_texts)}")
            print(f"  Final text: {final_text or '(none)'}")
            
            if assistant_response:
                print(f"\n🤖 Assistant Response:")
                result = assistant_response.get("result", {})
                meta = assistant_response.get("meta", {})
                
                print(f"  Status: {meta.get('status', 'unknown')}")
                print(f"  Decision time: {meta.get('decision_ms', 0)}ms")
                print(f"  Intent: {result.get('intent', 'unknown')}")
                print(f"  Action: {result.get('action', 'unknown')}")
                print(f"  Confidence: {result.get('confidence', 0):.2%}")
                
                # Check for LLM ranking
                data = result.get("data", {})
                ranking = data.get("ranking")
                
                if ranking:
                    print(f"\n✨ LLM Ranking (Voice Mode):")
                    print(f"  Mode: {ranking.get('mode', 'unknown')}")
                    print(f"  Ranked hotels: {len(ranking.get('ranked_hotels', []))}")
                    
                    llm_response = ranking.get("llm_response", "")
                    if llm_response:
                        print(f"\n  🎙️  Voice Response (TTS-optimized):")
                        print(f"  \"{llm_response}\"")
                    
                    if ranking.get("llm_error"):
                        print(f"  ⚠️  LLM Error: {ranking['llm_error']}")
                    
                    # Show top ranked hotels
                    ranked_hotels = ranking.get("ranked_hotels", [])
                    if ranked_hotels:
                        print(f"\n  🏨 Top Ranked Hotels:")
                        for i, hotel in enumerate(ranked_hotels[:3], 1):
                            name = hotel.get("name", "Unknown")
                            rating = hotel.get("rating", "N/A")
                            location = hotel.get("location", "N/A")
                            print(f"    {i}. {name} - {rating}⭐ ({location})")
                else:
                    print(f"\n  ℹ️  No LLM ranking (action may be ASK_LOCATION/ASK_DATES/FALLBACK)")
                
                # Full response for debugging
                print(f"\n📋 Full Response (JSON):")
                print(json.dumps(assistant_response, indent=2))
            
            else:
                print(f"\n❌ No assistant response received")
            
            print_section("TEST COMPLETE")
            return assistant_response is not None
    
    except Exception as e:
        print(f"\n❌ Test failed with error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run the voice endpoint test."""
    import sys
    
    wav_file = sys.argv[1] if len(sys.argv) > 1 else None
    success = await test_voice_stream(wav_file)
    
    exit_code = 0 if success else 1
    print(f"\nExit code: {exit_code}")
    return exit_code


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
