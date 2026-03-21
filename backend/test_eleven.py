"""Quick test script to verify ElevenLabs TTS setup"""
import asyncio
from backend.services.eleven_tts import ElevenLabsTTS, ElevenTTSConfig
from backend.config import ELEVEN_API_KEY

async def test_tts():
    api_key = ELEVEN_API_KEY
    print(f"API Key (first 10 chars): {api_key[:10]}..." if api_key else "❌ No API key found")
    
    if not api_key:
        print("Add ELEVENLABS_API_KEY to your .env file")
        return
    
    cfg = ElevenTTSConfig(
        api_key=api_key,
        voice_id="21m00Tcm4TlvDq8ikWAM"  # Rachel voice
    )
    
    tts = ElevenLabsTTS(cfg)
    
    print("\n🎤 Testing TTS with 'Hello world'...")
    try:
        chunk_count = 0
        import asyncio
        async def run_test():
            nonlocal chunk_count
            async for event in tts.stream_audio("Hello world"):
                msg_type = event.get("message_type")
                print(f"  Received: {msg_type}")
                
                if msg_type == "audio":
                    chunk_count += 1
                elif msg_type == "metadata":
                    print(f"    Metadata: {event.get('data', {})}")
                elif msg_type == "error":
                    print(f"  ❌ Error: {event.get('error')}")
                    return
                elif msg_type == "flush":
                    print(f"  ✅ Success! Received {chunk_count} audio chunks")
                    return
        
        # Add timeout
        await asyncio.wait_for(run_test(), timeout=15.0)
                
    except asyncio.TimeoutError:
        print(f"  ⏱️ Timeout after receiving {chunk_count} audio chunks (stream may not have ended properly)")
    except Exception as e:
        print(f"❌ Exception: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_tts())
