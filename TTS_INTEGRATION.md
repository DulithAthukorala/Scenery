# ElevenLabs TTS Integration

## Overview
The TTS (Text-to-Speech) service has been integrated into the voice router to provide audio responses using ElevenLabs API.

## Files Created/Modified

### New Files:
1. **`backend/services/eleven_tts.py`** - ElevenLabs TTS service
   - `ElevenTTSConfig`: Configuration dataclass for TTS settings
   - `ElevenLabsTTS`: Main TTS class for streaming audio
   - `stream_audio()`: Streams audio chunks from text
   - `synthesize_to_bytes()`: Convenience method to get complete audio

2. **`backend/scripts/test_tts.py`** - Test script for TTS functionality

### Modified Files:
1. **`backend/config.py`** - Added TTS configuration variables:
   - `ELEVEN_TTS_VOICE_ID` (default: "21m00Tcm4TlvDq8ikWAM" - Rachel voice)
   - `ELEVEN_TTS_MODEL_ID` (default: "eleven_turbo_v2_5")
   - `ELEVEN_TTS_STABILITY` (default: 0.5)
   - `ELEVEN_TTS_SIMILARITY_BOOST` (default: 0.75)
   - `ELEVEN_TTS_OPTIMIZE_LATENCY` (default: 4)

2. **`backend/routers/voice.py`** - Integrated TTS into voice streaming:
   - Imports TTS service and config
   - Modified `call_decision_and_respond()` to send audio after text response
   - Sends WebSocket messages: `tts_start`, `tts_audio`, `tts_end`, `tts_error`

## Configuration

Add these optional environment variables to `backend/.env`:

```bash
# TTS Configuration (all optional, have defaults)
ELEVEN_TTS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # Rachel voice
ELEVEN_TTS_MODEL_ID=eleven_turbo_v2_5
ELEVEN_TTS_STABILITY=0.5                    # 0-1, voice consistency
ELEVEN_TTS_SIMILARITY_BOOST=0.75            # 0-1, voice clarity
ELEVEN_TTS_OPTIMIZE_LATENCY=4               # 0-4, higher = lower latency
```

## Available ElevenLabs Voices

Popular voices you can use:
- `21m00Tcm4TlvDq8ikWAM` - Rachel (default, warm female)
- `AZnzlk1XvdvUeBnXmlld` - Domi (strong female)
- `EXAVITQu4vr4xnSDxMaL` - Bella (soft female)
- `ErXwobaYiN019PkySvjV` - Antoni (male)
- `MF3mGyEYCl7XYWbV9V6O` - Elli (young female)
- `TxGEqnHWrfWFTfGW9XjX` - Josh (male, professional)
- `VR6AewLTigWG4xSOukaG` - Arnold (crisp male)
- `pNInz6obpgDQGcFmaJgB` - Adam (deep male)

Find more voices at: https://elevenlabs.io/voice-library

## WebSocket Message Flow

### Client → Server (STT):
1. Audio chunks (bytes)
2. `{"type": "audio_end"}` when done speaking

### Server → Client (Response):
1. `{"type": "partial_text", "text": "..."}` - Partial transcription
2. `{"type": "final_text", "text": "..."}` - Final transcription
3. `{"type": "assistant_response", "result": {...}}` - Text response
4. `{"type": "tts_start"}` - Starting audio synthesis
5. `{"type": "tts_audio", "audio": "base64..."}` - Audio chunks (base64 PCM)
6. `{"type": "tts_end"}` - Audio synthesis complete
7. (Optional) `{"type": "tts_error", "error": "..."}` - TTS error

## Audio Format

The TTS returns **PCM audio** (16kHz, 16-bit) encoded as base64 strings. To play in browser:

```javascript
// Decode base64 to binary
const audioData = atob(base64String);
const arrayBuffer = new ArrayBuffer(audioData.length);
const view = new Uint8Array(arrayBuffer);
for (let i = 0; i < audioData.length; i++) {
    view[i] = audioData.charCodeAt(i);
}

// Create audio context and play
const audioContext = new AudioContext({sampleRate: 16000});
const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
const source = audioContext.createBufferSource();
source.buffer = audioBuffer;
source.connect(audioContext.destination);
source.start();
```

## Testing

Run the test script:

```bash
source venv/bin/activate
cd backend
python scripts/test_tts.py
```

Expected output:
```
🎤 Testing ElevenLabs TTS Service...
Voice ID: 21m00Tcm4TlvDq8ikWAM
Model: eleven_turbo_v2_5

📝 Converting text to speech: 'Hello! I am your travel assistant...'
  🔊 Received audio chunk #1 (size: 12000 chars base64)
  🔊 Received audio chunk #2 (size: 12000 chars base64)
  ...
  ✅ Stream completed (flush received)

✅ Test completed! Received X audio chunks
```

## Implementation Details

### ElevenTTS Service Structure
Similar to `eleven_stt.py`, the TTS service:
- Uses WebSocket for streaming audio
- Implements async generators for chunked audio
- Handles connection errors gracefully
- Supports SSML parsing for advanced voice control

### Voice Router Integration
The `call_decision_and_respond()` function now:
1. Processes user's voice input via STT
2. Calls decision layer to get text response
3. Sends text response to client
4. **NEW**: Synthesizes text to audio via TTS
5. Streams audio chunks to client
6. Signals completion with `tts_end`

### Error Handling
- TTS errors don't crash the WebSocket connection
- Errors are logged and sent to client as `tts_error` messages
- Text response is always sent even if TTS fails

## Frontend Integration

Update `voice.js` or `voice.html` to handle TTS messages:

```javascript
let audioChunks = [];

websocket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'tts_start') {
        audioChunks = [];
        console.log('Starting audio playback...');
    }
    else if (data.type === 'tts_audio') {
        audioChunks.push(data.audio);
    }
    else if (data.type === 'tts_end') {
        playAudio(audioChunks);
    }
    else if (data.type === 'tts_error') {
        console.error('TTS Error:', data.error);
    }
};

function playAudio(chunks) {
    // Combine all base64 chunks and play
    const combined = chunks.join('');
    // Decode and play as shown above
}
```

## Next Steps

1. ✅ Create TTS service (`eleven_tts.py`)
2. ✅ Update config with TTS settings
3. ✅ Integrate TTS into voice router
4. ✅ Create test script
5. 🔲 Update frontend to play TTS audio
6. 🔲 Add voice selection UI
7. 🔲 Add audio playback controls (pause, stop, volume)
8. 🔲 Handle audio queueing for multiple responses

## Troubleshooting

**No audio received:**
- Check `ELEVEN_API_KEY` is set correctly
- Verify API key has TTS permissions
- Check console for `tts_error` messages

**Poor audio quality:**
- Increase `ELEVEN_TTS_OPTIMIZE_LATENCY` (0-4)
- Adjust `ELEVEN_TTS_STABILITY` for consistency
- Try different voice IDs

**High latency:**
- Use `eleven_turbo_v2_5` model (fastest)
- Set `ELEVEN_TTS_OPTIMIZE_LATENCY=4`
- Ensure good network connection
