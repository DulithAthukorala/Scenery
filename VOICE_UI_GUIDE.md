# Voice UI - User Guide

## Beautiful Voice Interface with TTS

The voice UI has been completely redesigned with a modern, beautiful interface that includes:

### 🎨 Visual Features

1. **Animated Microphone Button**
   - **Default State**: Brown gradient (brand colors)
   - **Recording State**: Red pulsing animation
   - **Speaking State**: Green pulsing animation with sound waves
   - Smooth hover effects and transitions

2. **Audio Visualization**
   - 7 animated wave bars
   - Activates during recording and TTS playback
   - Smooth animations synced with audio state

3. **Status Indicators**
   - Real-time connection status
   - Animated status dot with pulse effect
   - Color-coded states (connected/error/disconnected)

4. **Message Bubbles**
   - User messages: Brown gradient, aligned right
   - Assistant messages: Green gradient, aligned left
   - System messages: Yellow highlight, centered
   - Slide-in animations for new messages

5. **Hotel Cards**
   - Grid layout with hover effects
   - Glassmorphism design
   - Rating badges and location pins
   - Smooth elevation on hover

### 🎙️ How It Works

1. **Click the microphone** → Button turns red and pulses
2. **Speak your query** → Voice waves animate
3. **Click again to stop** → Audio is processed
4. **Receive text response** → Appears as assistant message
5. **Listen to audio response** → Button turns green, TTS plays automatically

### 🔊 TTS Audio Playback

The interface now includes full text-to-speech audio playback:

- **Automatic playback** of assistant responses
- **Visual feedback** with green pulsing button
- **Wave animations** during speech
- **PCM audio decoding** (16kHz, 16-bit)
- **Prevents recording** while assistant is speaking

### 🎯 States

| State | Button Color | Animation | Status |
|-------|-------------|-----------|---------|
| Idle | Brown | None | Ready to record |
| Recording | Red | Pulse + Waves | "🔴 Recording..." |
| Processing | Brown | None | "Processing..." |
| Speaking | Green | Pulse + Waves | "🔊 Assistant speaking..." |

### 🛠️ Technical Details

**Audio Handling:**
- Recording: WebRTC MediaRecorder API
- Playback: Web Audio API
- Format: PCM 16kHz 16-bit mono
- Base64 encoding for WebSocket transport

**Visual Effects:**
- Glassmorphism (backdrop-filter blur)
- CSS animations and transitions
- Gradient backgrounds
- Shadow effects
- Responsive design

### 📱 Responsive Design

- Desktop: Full-sized buttons and spacious layout
- Mobile: Smaller buttons, optimized spacing
- Adaptive grid for hotel cards
- Touch-friendly controls

### 🎨 Color Scheme

**Brand Colors:**
- Primary: Brown (#8B7355 to #5E4A35)
- Secondary: Tan (#C7B08A)
- Accent: Cream (#E8DCC7)

**State Colors:**
- Recording: Red (#ff6b6b to #c92a2a)
- Speaking: Green (#51cf66 to #2f9e44)
- Error: Red tones
- Success: Green tones

### 💡 Tips for Best Experience

1. **Use Chrome or Edge** for best Web Audio API support
2. **Allow microphone permissions** when prompted
3. **Wait for audio to finish** before recording again
4. **Keep sessions short** for better voice recognition
5. **Speak clearly** at a normal pace

### 🔧 Customization

To customize the voice or TTS settings, update your `backend/.env`:

```bash
ELEVEN_TTS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # Rachel (default)
ELEVEN_TTS_MODEL_ID=eleven_turbo_v2_5
ELEVEN_TTS_STABILITY=0.5
ELEVEN_TTS_SIMILARITY_BOOST=0.75
ELEVEN_TTS_OPTIMIZE_LATENCY=4
```

### 🚀 Usage

1. Start backend:
   ```bash
   cd backend
   python main.py
   ```

2. Open frontend:
   ```bash
   # Open in browser
   open frontend/voice.html
   # Or use a local server
   python -m http.server 3000 --directory frontend
   ```

3. Click microphone and start talking!

### 🎬 Demo Flow

**Example conversation:**

1. **You (click mic)**: "Show me luxury hotels in Colombo"
   - Red pulsing button, waves animate
   
2. **Processing**: "Processing..." status
   - Brief pause while STT + AI + TTS process

3. **Assistant (auto-plays)**: "I found several luxury hotels..."
   - Green pulsing button
   - Waves animate during speech
   - Hotel cards appear below

4. **Ready**: Button returns to brown, ready for next query

### 🐛 Troubleshooting

**No audio playback:**
- Check browser console for errors
- Verify ELEVEN_API_KEY is set
- Ensure backend is running
- Try refreshing the page

**Microphone not working:**
- Grant microphone permissions
- Check system microphone settings
- Try different browser

**WebSocket errors:**
- Ensure backend is running on port 8000
- Check firewall settings
- Verify SSL certificates (for HTTPS)

### 📊 Performance

- **STT Latency**: ~500ms (depends on audio length)
- **AI Processing**: ~1-3s (depends on query complexity)
- **TTS Generation**: ~500ms-1s (depends on text length)
- **Total Round Trip**: ~2-5s typical

Enjoy your beautiful voice interface! 🎉
