"""
Simple test script for ElevenLabs TTS service.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import backend modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.config import ELEVEN_API_KEY, ELEVEN_TTS_VOICE_ID, ELEVEN_TTS_MODEL_ID
from backend.config import ELEVEN_TTS_STABILITY, ELEVEN_TTS_SIMILARITY_BOOST, ELEVEN_TTS_OPTIMIZE_LATENCY
from backend.services.eleven_tts import ElevenLabsTTS, ElevenTTSConfig


async def test_tts_stream():
    """Test TTS streaming with a simple text."""
    if not ELEVEN_API_KEY:
        print("❌ ELEVEN_API_KEY not set in .env file")
        return
    
    print("🎤 Testing ElevenLabs TTS Service...")
    print(f"Voice ID: {ELEVEN_TTS_VOICE_ID}")
    print(f"Model: {ELEVEN_TTS_MODEL_ID}")
    
    cfg = ElevenTTSConfig(
        api_key=ELEVEN_API_KEY,
        voice_id=ELEVEN_TTS_VOICE_ID,
        model_id=ELEVEN_TTS_MODEL_ID,
        stability=ELEVEN_TTS_STABILITY,
        similarity_boost=ELEVEN_TTS_SIMILARITY_BOOST,
        optimize_streaming_latency=ELEVEN_TTS_OPTIMIZE_LATENCY,
    )
    
    tts = ElevenLabsTTS(cfg)
    
    test_text = "Hello! I am your travel assistant. How can I help you find the perfect hotel today?"
    print(f"\n📝 Converting text to speech: '{test_text}'")
    
    audio_chunks = 0
    try:
        async for event in tts.stream_audio(test_text):
            msg_type = event.get("message_type")
            
            if msg_type == "audio":
                audio_chunks += 1
                audio_data = event.get("audio", "")
                audio_size = len(audio_data) if audio_data else 0
                print(f"  🔊 Received audio chunk #{audio_chunks} (size: {audio_size} chars base64)")
            elif msg_type == "flush":
                print("  ✅ Stream completed (flush received)")
                break
            elif msg_type == "error":
                print(f"  ❌ Error: {event.get('error')}")
                break
            elif msg_type == "metadata":
                print(f"  ℹ️  Metadata: {event.get('data')}")
        
        print(f"\n✅ Test completed! Received {audio_chunks} audio chunks")
        
    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {e}")


async def test_tts_bytes():
    """Test TTS with synthesize_to_bytes convenience method."""
    if not ELEVEN_API_KEY:
        print("❌ ELEVEN_API_KEY not set in .env file")
        return
    
    print("\n🎤 Testing TTS with synthesize_to_bytes...")
    
    cfg = ElevenTTSConfig(
        api_key=ELEVEN_API_KEY,
        voice_id=ELEVEN_TTS_VOICE_ID,
        model_id=ELEVEN_TTS_MODEL_ID,
        stability=ELEVEN_TTS_STABILITY,
        similarity_boost=ELEVEN_TTS_SIMILARITY_BOOST,
        optimize_streaming_latency=ELEVEN_TTS_OPTIMIZE_LATENCY,
    )
    
    tts = ElevenLabsTTS(cfg)
    
    test_text = "This is a quick test of the text to speech synthesis."
    print(f"📝 Text: '{test_text}'")
    
    try:
        audio_bytes = await tts.synthesize_to_bytes(test_text)
        print(f"✅ Synthesized audio: {len(audio_bytes)} bytes")
        
        # Optionally save to file
        # output_file = Path(__file__).parent / "test_output.pcm"
        # output_file.write_bytes(audio_bytes)
        # print(f"💾 Saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Test failed: {type(e).__name__}: {e}")


async def main():
    await test_tts_stream()
    await test_tts_bytes()


if __name__ == "__main__":
    asyncio.run(main())
