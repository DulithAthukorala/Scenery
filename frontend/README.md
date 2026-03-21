# Scenery Frontend

Plain HTML / CSS / JS — no Node.js, no npm, no build tools.

## Pages

| File | Purpose |
|------|---------|
| `index.html` | Landing page |
| `chat.html` + `chat.js` | Text chat interface (POST /chat) |
| `voice.html` + `voice.js` | Voice interface — Pipecat + Daily WebRTC pipeline |
| `search.html` + `search.js` | Advanced hotel search with filters |
| `styles.css` | Shared glassmorphism design system |

---

## How to Run

### Prerequisites — add these to `backend/.env`

```
GEMINI_API_KEY=...
GROQ_API_KEY=...
RAPIDAPI_KEY=...
RAPIDAPI_HOST=...
ELEVEN_API_KEY=...
DAILY_API_KEY=...          # get a free key at dashboard.daily.co
DAILY_BOT_URL=http://localhost:8100
```

### Terminal 1 — Pipecat bot (Docker, Linux)

The Pipecat voice pipeline runs in a Linux Docker container because the
`daily-python` WebRTC library has no Windows wheels.

```bash
# From the project root
docker compose up --build bot
```

Bot runner is now listening on port 8100.

### Terminal 2 — FastAPI backend (Windows)

```bash
cd path/to/Scenery
python -m uvicorn backend.main:app --reload --port 8000
```

### Terminal 3 — Serve the frontend

```bash
cd frontend
python -m http.server 3000
```

Open http://localhost:3000

---

## Architecture

```
Browser
 ├─ chat.html   → POST /chat                  (text, HTTP)
 ├─ search.html → GET  /localdb/hotels/...    (HTTP)
 └─ voice.html  → POST /voice/room            (get Daily room URL)
                → Daily JS SDK (WebRTC audio) ↔ Daily.co cloud
                                              ↔ Pipecat bot (port 8100)
                                                 ElevenLabs STT
                                                 → decision engine (decision.py)
                                                 → Gemini LLM
                                                 ElevenLabs TTS
                                              ← hotel cards via Daily app-message
```

### Voice flow (step by step)

1. `voice.html` loads → calls `POST /voice/room` on FastAPI
2. FastAPI creates a Daily.co room (1-hour TTL), generates tokens, tells the bot container to start
3. Pipecat bot joins the room via WebRTC
4. Browser joins via `@daily-co/daily-js` SDK — no iframe, headless call object
5. User clicks mic → `call.setLocalAudio(true)` → audio streams to bot over WebRTC
6. Bot's Silero VAD detects end of speech → ElevenLabs STT transcribes it
7. `HotelQueryProcessor` calls `handle_query()` → hotel data + Gemini response
8. Bot sends hotel cards to browser via Daily **app message** (no extra socket needed)
9. ElevenLabs TTS generates speech → bot outputs audio back through WebRTC
10. Browser plays bot audio automatically (Daily SDK handles it)
11. `active-speaker-change` event updates the mic button UI

---

## API Endpoints

| Method | Path | Used by |
|--------|------|---------|
| `GET` | `/health` | — |
| `POST` | `/chat` | chat.js, voice.js (live prices form) |
| `POST` | `/voice/room` | voice.js on page load |
| `WS` | `/voice/stream` | legacy fallback (not used by voice.html) |
| `GET` | `/localdb/hotels/insights` | search.js |
| `GET` | `/rapidapi/hotels/insights` | search.js |

---

## Troubleshooting

### "Room creation failed" on voice page
- Check `DAILY_API_KEY` is set in `backend/.env`
- Check the bot container is running: `docker ps` → should show `scenery-bot`
- Check bot logs: `docker compose logs bot`

### "DAILY_BOT_URL not configured"
- Ensure `DAILY_BOT_URL=http://localhost:8100` is in `backend/.env`

### Bot container exits immediately
- Usually a missing env var. Run:
  ```bash
  docker compose logs bot
  ```
  Common culprits: `RAPIDAPI_KEY`, `GEMINI_API_KEY`, `ELEVEN_API_KEY`

### Chat or search not working
- Verify backend is running: `curl http://localhost:8000/health`
- Open browser DevTools → Console for error messages

### CORS errors
Already configured in `backend/main.py`. If you still see CORS errors, make
sure you're accessing the frontend via `http://localhost:3000` (not `file://`).

---

## Making Changes

| What | Where |
|------|-------|
| Colors / design | `styles.css` — edit the CSS variables at the top |
| Chat logic | `chat.js` |
| Voice UI | `voice.js` — UI functions are at the bottom; transport layer is at the top |
| Hotel pipeline | `backend/bot/hotel_processor.py` |
| Pipecat pipeline config | `backend/bot/pipecat_bot.py` |
| Intent / routing logic | `backend/core/decision.py` |

After any Python change, FastAPI reloads automatically (`--reload`).
After any bot change, rebuild: `docker compose up --build bot`.
After any frontend change, just refresh the browser.
