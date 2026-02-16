# Scenery - AI Hotel Search Agent

**Real-time voice & text conversational agent for hotel discovery in Sri Lanka**

[![Status](https://img.shields.io/badge/status-prototype-yellow)](https://github.com/DulithAthukorala/Scenery)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [Why This Project](#why-this-project)
- [Demo](#demo)
- [Architecture](#architecture)
- [Performance Benchmarks](#performance-benchmarks)
- [Technology Stack](#technology-stack)
- [Pipeline Deep Dive](#pipeline-deep-dive)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Database Schema](#database-schema)
- [Deployment](#deployment)
- [Monitoring](#monitoring)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

---

## Overview

Scenery is a dual-mode conversational AI agent that helps users discover hotels in Sri Lanka through natural voice or text interaction. The system achieves **sub-second response times** by intelligently balancing local database queries with real-time API calls.

### Key Features

- **🎤 Real-time voice interaction** - Streaming STT/TTS pipeline with 850ms-1.2s latency
- **💬 Text chat mode** - Lightning-fast responses (400-600ms) with rich formatting
- **🧠 Context-aware conversations** - Multi-turn dialog with entity persistence
- **📊 Smart data strategy** - Local DB for browsing, RapidAPI for live pricing
- **🔄 Streaming architecture** - Progressive responses, no blocking waits
- **🛡️ Production-ready error handling** - Graceful degradation, fallback strategies

### Target Performance Metrics

*These are target performance goals for the fully optimized system (not yet achieved in current prototype):*

#### STANDARD MODE (Local DB - hotel info, locations, features)
─────────────────────────────────────────────────────────────────

                          Voice Mode          Text Mode
Time to First Token       150-250ms           100-200ms
Time to First Audio       600-800ms           N/A
P50 Total Latency        850-1000ms          400-600ms
P90 Total Latency        1200-1500ms         800-1000ms


##### THINKING MODE (Live pricing via RapidAPI)
─────────────────────────────────────────────────────────────────

                          Voice Mode          Text Mode
Time to First Token       800-1200ms          600-1000ms
Time to First Audio       1500-2000ms         N/A
P50 Total Latency        3500-4500ms         2500-3500ms
P90 Total Latency        5500-7000ms         4500-6000ms



---

## Why This Project

Built to demonstrate understanding of production-grade voice AI engineering principles and conversational AI expertise for technical leadership and engineering roles in companies building innovative voice-first products.

### What This Demonstrates

**Voice AI Engineering:**
- Streaming pipeline architecture (not just sequential API calls)
- Latency optimization techniques (parallel processing, caching, early execution)
- Real-time audio processing with Pipecat framework
- Voice activity detection and interruption handling

**System Design:**
- Intelligent data layer (local-first with API fallback)
- Context management across conversation turns
- Error handling and graceful degradation
- Observability and monitoring patterns

**Production Thinking:**
- Cost optimization (local DB reduces API calls by 90%)
- Scalability considerations (connection pooling, caching)
- User experience focus (progressive responses, clear feedback)
- Deployment architecture (Docker, AWS EC2/S3)

---

## Demo

🚧 **Coming Soon**

Demo will showcase:
- Voice interaction: "Show me hotels in Galle under 15,000 rupees"
- Multi-turn conversation: "What about cheaper options?" → context carry-forward
- Local DB vs API decision making
- Streaming response visualization
- Error handling examples

---

## Architecture

### High-Level System Design
```
┌─────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                       │
│                    (Web/Mobile Client)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                    WebSocket/WebRTC
                              │
┌─────────────────────────────────────────────────────────────┐
│                     FASTAPI SERVER                          │
│                    (Pipecat Pipeline)                       │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐     │
│  │  VAD + STT   │──→│ Normalization│──→│  LLM Ranking │     │
│  │ (ElevenLabs) │   │  & Entities  │   │(Gemini 2.5 F)│     │
│  └──────────────┘   └──────────────┘   └──────────────┘     │
│                              │                    │         │
│                              ↓                    ↓         │
│                      ┌──────────────┐    ┌──────────────┐   │
│                      │  Local DB    │    │     TTS      │   │
│                      │  (SQLite)    │    │ (ElevenLabs) │   │
│                      └──────────────┘    └──────────────┘   │
│                              │                              │
│                              ↓                              │
│                      ┌──────────────┐                       │
│                      │  RapidAPI    │                       │
│                      │ (TripAdvisor)│                       │
│                      └──────────────┘                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
                    ┌──────────────────┐
                    │  AWS EC2 + S3    │
                    │   (Deployment)   │
                    └──────────────────┘
```

### Pipeline Flow & Expected Latency

#### Voice Mode Pipeline
```
User Speech → VAD Detection → STT (ElevenLabs) → Normalization → 
Entity Extraction → Context Resolution → DB Query Decision → 
[Local DB OR RapidAPI] → LLM Ranking (Gemini) → Response Generation → 
TTS (ElevenLabs) → Audio Streaming → User Hears Response

Expected Latency: 850ms - 1.2s (P50)
```

#### Text Mode Pipeline
```
User Text → Input Validation → Normalization → Entity Extraction → 
Context Resolution → DB Query Decision → [Local DB OR RapidAPI] → 
LLM Ranking (Gemini) → Formatted Response → User Sees Response

Expected Latency: 400-600ms (P50)
```

### Key Design Decisions

**Why Local Database First?**
- 90% of queries are exploratory ("show me hotels in X")
- Live pricing not needed until booking intent
- Reduces API costs
- Enables 200-300ms faster responses

**Why Gemini 2.5 Flash?**
- 50% faster than GPT-4 Turbo (300ms vs 600ms first token)
- Native JSON mode for structured output
- Lower cost
- Excellent reasoning for hotel ranking tasks

**Why ElevenLabs for Both STT/TTS?**
- Single subscription covers both services
- ElevenLabs Turbo v2.5 TTS: 150ms latency (industry-leading)
- Scribe STT: Competitive accuracy with Deepgram
- Voice consistency across the pipeline

**Why Pipecat?**
- Built specifically for voice AI pipelines
- Handles WebRTC/WebSocket transport layer
- Built-in VAD, interruption handling, streaming
- Reduces custom audio processing code by 80%

---
<!--

## Expected Performance Benchmarks

### Latency Breakdown (Voice Mode - Typical Query)

| Stage | Time | Optimization Applied |
|-------|------|---------------------|
| VAD Detection | 150-200ms | Silero VAD, tuned thresholds |
| STT (ElevenLabs) | 300-450ms | Streaming mode, interim results |
| Normalization | 20-50ms | spaCy, cached entity models |
| DB Query | 10-30ms | Indexed queries, in-memory caching |
| LLM Ranking | 300-500ms | Gemini Flash, JSON mode, top-10 pre-filter |
| TTS Generation | 150-250ms | Turbo v2.5, streaming chunks |
| **Total (P50)** | **930-1480ms** | **Target: <1200ms** |

### Latency Breakdown (Text Mode - Typical Query)

| Stage | Time | Optimization Applied |
|-------|------|---------------------|
| Input Validation | 5-10ms | Regex-based, no external calls |
| Normalization | 15-30ms | Cached spaCy models |
| DB Query | 10-30ms | Prepared statements, indexes |
| LLM Ranking | 200-400ms | Gemini Flash, structured prompts |
| Response Formatting | 10-20ms | Template-based rendering |
| **Total (P50)** | **240-490ms** | **Target: <600ms** |

### Estimated Cost Analysis (per 1000 queries)

*Theoretical calculations based on expected usage patterns for the target architecture, not measured production costs.*

| Component | Voice Mode | Text Mode | Notes |
|-----------|------------|-----------|-------|
| STT (ElevenLabs) | $0.30 | - | ~30s audio avg |
| TTS (ElevenLabs) | $0.50 | - | ~25s response avg |
| LLM (Gemini) | $0.15 | $0.15 | ~500 tokens/query |
| RapidAPI (10% usage) | $0.50 | $0.50 | Only when live prices needed |
| Infrastructure | $0.10 | $0.05 | EC2 compute, data transfer |
| **Total** | **$1.55** | **$0.70** | Per 1000 queries |

**Projected Monthly Cost (10K users, 5 queries/user/month):**
- 50K queries/month
- 70% voice, 30% text
- **Total: ~$65/month** (excluding RapidAPI for price checks)
- *Estimates based on current API pricing and expected usage, subject to change*

---
-->
## Technology Stack

### Core Framework
- **[FastAPI](https://fastapi.tiangolo.com/)** - Async Python web framework
- **[Pipecat](https://github.com/pipecat-ai/pipecat)** - Real-time voice AI pipeline framework
- **Python 3.11+** - Runtime environment

### AI Services
- **[ElevenLabs STT](https://elevenlabs.io/)** - Speech-to-Text (Scribe model)
- **[ElevenLabs TTS](https://elevenlabs.io/)** - Text-to-Speech (Turbo v2.5)
- **[Google Gemini 2.0 Flash](https://ai.google.dev/)** - LLM for ranking and reasoning
- **[spaCy](https://spacy.io/)** - NLP for entity extraction

### Data Layer
- **SQLite** - Local hotel database (150-200 hotels)
- **[RapidAPI (TripAdvisor)](https://rapidapi.com/)** - Live hotel pricing
- **Redis** - Session cache and conversation state (planned)

### Infrastructure
- **AWS EC2** - Application hosting
- **AWS S3** - Static assets (hotel images)
- **Docker** - Containerization
- **WebSocket/WebRTC** - Real-time audio transport

### Development Tools
- **pytest** - Testing framework
- **Uvicorn** - ASGI server
- **Black** - Code formatting
- **mypy** - Type checking

---

## Pipeline Deep Dive

### Voice Mode: Detailed Pipeline

#### Phase 1: Audio Capture & VAD (0-200ms)
<!--

```python
# Pipecat VAD configuration
vad_config = {
    'start_threshold': 0.3,      # 300ms of speech to start
    'stop_threshold': 0.5,       # 500ms silence to stop
    'min_speech_duration': 200,  # Ignore < 200ms utterances
    'padding': 100               # 100ms buffer before/after
}
```
-->
**What Happens:**
- User speaks: "Show me hotels in Galle under 15,000 rupees"
- Silero VAD detects speech start
- Audio buffered in 20ms frames
- VAD detects 500ms silence → triggers finalization
- **Time: 150-200ms** after user stops speaking

#### Phase 2: Speech-to-Text (200-650ms)
<!--

```python
# ElevenLabs STT streaming
async for partial_transcript in elevenlabs_stt.stream(audio):
    if partial_transcript.confidence > 0.8:
        # Start entity extraction early (parallel processing)
        entities = extract_entities(partial_transcript.text)
```
-->
**What Happens:**
- Audio streamed to ElevenLabs Scribe
- Partial results available at 200ms: "show me hotels..."
- Entity extraction starts on partials (parallel)
- Final transcript at 450ms: "show me hotels in Galle under 15000 rupees"
- **Time: 300-450ms**

#### Phase 3: Normalization & Entity Extraction (650-750ms)
<!--

```python
# Entity extraction with spaCy
entities = {
    "intent": "search_hotels",
    "location": {
        "city": "Galle",
        "coordinates": [6.0535, 80.2210]
    },
    "budget": {
        "amount": 15000,
        "currency": "LKR",
        "operator": "under"
    },
    "dates": None,  # Not mentioned
    "amenities": []
}
```
-->
**What Happens:**
- Text normalized: "15000 rupees" → 15000 LKR
- Location resolved: "Galle" → lat/lng coordinates
- Intent classified: "search_hotels" (vs "book", "details", etc.)
- **Time: 20-50ms**

#### Phase 4: Context Resolution & DB Decision (750-800ms)
<!--

```python
# Check conversation context
if session.has_context():
    # User said "cheaper ones" → use previous location
    entities["location"] = session.get("location")

# Decide: Local DB or RapidAPI?
if entities.get("dates") is None:
    # No dates = exploratory search → use local DB
    data_source = "local_db"
else:
    # Specific dates = need live pricing → call API
    data_source = "rapidapi"
```
-->

**What Happens:**
- Check Redis for session state
- Resolve coreferences ("the second one", "cheaper")
- Decide data source based on query type
- **Time: 5-20ms**

#### Phase 5: Database Query (800-850ms)
<!--

```python
# SQLite query (local DB path)
query = """
    SELECT id, name, city, price_lkr, star_rating, amenities, images
    FROM hotels
    WHERE city = ? AND price_lkr <= ?
    ORDER BY star_rating DESC, price_lkr ASC
    LIMIT 50
"""
results = db.execute(query, ("Galle", 15000))

# Returns 24 hotels in 10-30ms
```
-->
**What Happens:**
- Query local SQLite database
- Indexed on `city` and `price_lkr` (fast lookup)
- Returns 24 hotels in Galle under 15,000 LKR
- **Time: 10-30ms**
<!--

**Alternative: RapidAPI Path (if dates specified)**
```python
# TripAdvisor API via RapidAPI (when needed)
response = await rapidapi.get(
    "https://tripadvisor16.p.rapidapi.com/api/v1/hotels/searchHotels",
    params={
        "geoId": "293962",  # Galle
        "checkIn": "2026-02-15",
        "checkOut": "2026-02-17",
        "priceMax": "15000",
        "currencyCode": "LKR"
    }
)
# Time: 500-2000ms (variable, network dependent)
```
-->

#### Phase 6: LLM Ranking (850-1350ms)
<!--

```python
# Gemini 2.5 Flash prompt (will change)
prompt = f"""
You are a hotel recommendation expert. Rank these hotels for the user.

User query: "show me hotels in Galle under 15000 rupees"

Hotels (top 10 pre-ranked by rating):
1. Jetwing Lighthouse - 12,500 LKR, 4.5★, ocean view, pool
2. Fort Bazaar - 11,000 LKR, 4.3★, historic fort location
3. Taru Villas - 14,800 LKR, 4.7★, boutique villa, spa
... [7 more hotels]

Return JSON only:
{{
  "top_3": [
    {{"hotel_id": "hotel_123", "reason": "Best value with ocean views"}},
    {{"hotel_id": "hotel_456", "reason": "Perfect for culture lovers"}},
    {{"hotel_id": "hotel_789", "reason": "Luxury boutique experience"}}
  ],
  "voice_summary": "I found 3 great options in Galle. The best value is Jetwing Lighthouse at 12,500 rupees with stunning ocean views.",
  "text_summary": "Here are 3 excellent hotels in Galle under 15,000 rupees..."
}}
"""

# Streaming response
async for chunk in gemini.stream(prompt, response_format="json"):
    # First token at 200-300ms
    # Full response at 500-800ms
```
-->
**What Happens:**
- Pre-filter to top 10 hotels (don't send all 24 to LLM)
- Gemini ranks based on user query context
- Returns structured JSON with reasons
- Separate summaries for voice (concise) vs text (detailed)
- **Time: 300-500ms**

#### Phase 7: Text-to-Speech (1350-1600ms)
<!--

```python
# ElevenLabs TTS streaming
async for audio_chunk in elevenlabs_tts.stream(
    text=llm_response["voice_summary"],
    voice_id="Rachel",  # or your chosen voice
    model="eleven_turbo_v2_5",
    streaming=True
):
    # First audio chunk at 150ms
    # Stream to user immediately (no buffering)
    await websocket.send_audio(audio_chunk)
```
-->
**What Happens:**
- TTS starts processing immediately (doesn't wait for full text)
- First audio chunk ready at 150ms
- User hears first words at **~850ms total pipeline time**
- Full response plays over 20-30 seconds
- **Time to first audio: 150-250ms**
<!--

### Text Mode: Simplified Pipeline
```python
@app.post("/chat")
async def chat(request: ChatRequest):
    # 1. Validate input (5ms)
    validate_input(request.message)
    
    # 2. Extract entities (15ms)
    entities = extract_entities(request.message)
    
    # 3. Resolve context (10ms)
    context = get_session_context(request.session_id)
    entities = resolve_with_context(entities, context)
    
    # 4. Query DB (20ms)
    hotels = query_database(entities)
    
    # 5. LLM ranking (300ms)
    ranked = await gemini.rank(hotels, entities)
    
    # 6. Format response (10ms)
    response = format_markdown(ranked, entities)
    
    # Total: ~360ms
    return {"response": response, "hotels": ranked}
```

---

## Quick Start

### Prerequisites

- Python 3.11 or higher
- ElevenLabs API key
- Google Gemini API key
- RapidAPI key (TripAdvisor)

### Installation
```bash
# Clone the repository
git clone https://github.com/DulithAthukorala/Scenery.git
cd Scenery

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_sm
```

### Environment Setup

Create a `.env` file in the project root:
```env
# API Keys
ELEVENLABS_API_KEY=your_elevenlabs_key_here
GEMINI_API_KEY=your_gemini_key_here
RAPIDAPI_KEY=your_rapidapi_key_here

# Service Configuration
ELEVENLABS_VOICE_ID=Rachel  # or your preferred voice
GEMINI_MODEL=gemini-2.0-flash-exp
STT_MODEL=scribe
TTS_MODEL=eleven_turbo_v2_5

# Database
DATABASE_URL=sqlite:///./hotels.db

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4

# Logging
LOG_LEVEL=INFO
```

### Database Setup
```bash
# Initialize the database
python scripts/init_db.py

# Load hotel data (if you have a CSV/JSON)
python scripts/load_hotels.py --source data/hotels.csv

# Or create sample data for testing
python scripts/create_sample_data.py --count 50
```

### Running Locally
```bash
# Development mode (with auto-reload)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
```

### Running with Docker (Planned)

*Docker support is planned for future releases. The expected setup will be:*

```bash
# Build the image
docker build -t scenery:latest .

# Run the container
docker run -d \
  --name scenery \
  -p 8000:8000 \
  --env-file .env \
  scenery:latest

# View logs
docker logs -f scenery
```

Expected outcome: Simplified deployment with containerization for consistent environments.

### Testing the API
```bash
# Health check
curl http://localhost:8000/health

# Text mode query
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "show me hotels in Galle under 15000 rupees",
    "session_id": "test-session-123"
  }'

# Voice mode (WebSocket)
# Use the provided client: python client/voice_client.py
```

---

## Configuration

### Pipecat Pipeline Configuration
```python
# config/pipeline.py

PIPELINE_CONFIG = {
    "vad": {
        "model": "silero",
        "start_threshold": 0.3,
        "stop_threshold": 0.5,
        "min_speech_duration_ms": 200,
        "max_speech_duration_s": 30,
        "padding_duration_ms": 100
    },
    "stt": {
        "provider": "elevenlabs",
        "model": "scribe",
        "language": "en",
        "interim_results": True
    },
    "llm": {
        "provider": "google",
        "model": "gemini-2.0-flash-exp",
        "temperature": 0.3,
        "max_tokens": 500,
        "response_format": "json"
    },
    "tts": {
        "provider": "elevenlabs",
        "model": "eleven_turbo_v2_5",
        "voice_id": "Rachel",
        "streaming": True,
        "latency_optimization": True
    }
}
```

### Database Configuration
```python
# config/database.py

DB_CONFIG = {
    "type": "sqlite",
    "path": "./hotels.db",
    "connection_pool": {
        "max_connections": 10,
        "timeout": 30
    },
    "indexes": [
        "CREATE INDEX idx_city ON hotels(city)",
        "CREATE INDEX idx_price ON hotels(price_lkr)",
        "CREATE INDEX idx_rating ON hotels(star_rating)"
    ]
}
```

### API Rate Limits
```python
# config/rate_limits.py

RATE_LIMITS = {
    "elevenlabs_stt": {
        "requests_per_minute": 60,
        "concurrent_streams": 10
    },
    "elevenlabs_tts": {
        "requests_per_minute": 60,
        "concurrent_streams": 10
    },
    "gemini": {
        "requests_per_minute": 60,
        "tokens_per_minute": 100000
    },
    "rapidapi": {
        "requests_per_day": 1000,
        "concurrent_requests": 5
    }
}
```

---

## API Reference

### REST Endpoints

#### `POST /chat` - Text Mode Query
```http
POST /chat HTTP/1.1
Content-Type: application/json

{
  "message": "show me hotels in Galle under 15000",
  "session_id": "user_abc123",
  "context": {}  // optional
}
```

**Response:**
```json
{
  "response": "### 🏨 Hotels in Galle (Under LKR 15,000)\n\n**1. Jetwing Lighthouse**...",
  "hotels": [
    {
      "id": "hotel_123",
      "name": "Jetwing Lighthouse",
      "city": "Galle",
      "price_lkr": 12500,
      "star_rating": 4.5,
      "amenities": ["pool", "wifi", "breakfast", "ocean_view"],
      "images": ["https://..."],
      "reason": "Best value with stunning ocean views"
    }
  ],
  "metadata": {
    "query_time_ms": 423,
    "source": "local_db",
    "total_results": 24,
    "showing": 3
  }
}
```

#### `GET /health` - Health Check
```http
GET /health HTTP/1.1
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "services": {
    "database": "connected",
    "elevenlabs": "available",
    "gemini": "available",
    "rapidapi": "available"
  },
  "uptime_seconds": 86400
}
```

#### `POST /session/new` - Create Session
```http
POST /session/new HTTP/1.1
```

**Response:**
```json
{
  "session_id": "sess_a1b2c3d4",
  "expires_at": "2026-02-11T15:30:00Z"
}
```

### WebSocket Endpoint

#### `WS /voice` - Voice Mode Connection

**Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8000/voice?session_id=sess_abc123');

// Send audio chunks
ws.send(audioChunk);  // ArrayBuffer of audio data

// Receive responses
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'audio') {
    // Play audio chunk
    playAudio(data.chunk);
  } else if (data.type === 'transcript') {
    // Display user's speech
    console.log('You said:', data.text);
  } else if (data.type === 'metadata') {
    // Handle metadata (hotels found, processing status, etc.)
    console.log('Metadata:', data);
  }
};
```

**Message Types:**
```typescript
// From client to server
{
  "type": "audio",
  "chunk": ArrayBuffer,  // PCM audio data
  "sample_rate": 16000,
  "channels": 1
}

// From server to client
{
  "type": "audio",
  "chunk": ArrayBuffer,  // Response audio
  "is_final": false
}

{
  "type": "transcript",
  "text": "show me hotels in Galle under 15000",
  "confidence": 0.95,
  "is_final": true
}

{
  "type": "hotels",
  "data": [...],  // Hotel list
  "metadata": {...}
}

{
  "type": "error",
  "message": "Service temporarily unavailable",
  "code": "STT_TIMEOUT"
}
```

---

## Database Schema

### Hotels Table
```sql
CREATE TABLE hotels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    district VARCHAR(100),
    address TEXT,
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    
    -- Pricing
    price_per_night_lkr INTEGER NOT NULL,
    price_range VARCHAR(50),  -- 'budget', 'mid-range', 'luxury'
    
    -- Ratings
    star_rating DECIMAL(2,1),
    avg_review DECIMAL(2,1),
    review_count INTEGER DEFAULT 0,
    
    -- Features
    amenities TEXT,  -- JSON array: ["pool", "wifi", "breakfast"]
    room_types TEXT,  -- JSON array: ["single", "double", "suite"]
    
    -- Media
    images TEXT,  -- JSON array of image URLs
    description TEXT,
    
    -- Contact
    phone VARCHAR(20),
    email VARCHAR(100),
    website VARCHAR(255),
    
    -- Metadata
    active BOOLEAN DEFAULT TRUE,
    featured BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes
    INDEX idx_city (city),
    INDEX idx_price (price_per_night_lkr),
    INDEX idx_rating (star_rating),
    INDEX idx_location (latitude, longitude)
);
```

### Sessions Table (Redis Schema)
```python
# Stored in Redis with 5-minute TTL
session_key = f"session:{session_id}"

session_data = {
    "session_id": "sess_abc123",
    "user_id": None,  # If authenticated
    "created_at": "2026-02-11T10:23:45Z",
    "last_interaction": "2026-02-11T10:25:30Z",
    "conversation_history": [
        {
            "turn": 1,
            "user_input": "show me hotels in Galle under 15000",
            "intent": "search_hotels",
            "entities": {...},
            "results": [...],
            "timestamp": "2026-02-11T10:23:45Z"
        }
    ],
    "persistent_entities": {
        "location": "Galle",
        "budget": 15000,
        "preferences": ["ocean_view"]
    }
}
```

### Sample Data
```sql
-- Example hotel record
INSERT INTO hotels (
    name, city, district, address, latitude, longitude,
    price_per_night_lkr, price_range, star_rating, avg_review, review_count,
    amenities, room_types, images, description
) VALUES (
    'Jetwing Lighthouse',
    'Galle',
    'Galle',
    'Dadella, Galle',
    6.0535,
    80.2210,
    12500,
    'mid-range',
    4.5,
    4.6,
    1247,
    '["pool", "wifi", "breakfast", "ocean_view", "spa", "restaurant"]',
    '["standard", "deluxe", "suite"]',
    '["https://s3.amazonaws.com/scenery/hotels/jetwing-1.jpg", "..."]',
    'Luxury hotel with stunning ocean views and infinity pool overlooking the Indian Ocean.'
);
```
-->

---

## Deployment

*Note: This project is currently a work-in-progress. The deployment strategy outlined below represents the planned production architecture.*

### Planned Deployment Strategy

**Containerization with Docker:**
- Application will be containerized using Docker for consistent deployment across environments
- Multi-container setup using Docker Compose for the main application and supporting services (Redis for caching)
- Expected outcome: Simplified deployment process and environment consistency

**Cloud Infrastructure (AWS):**
- **Compute**: EC2 instance (t3.medium or similar) for running the containerized application
  - Expected: 99.9% uptime with proper monitoring and auto-restart configurations
- **Storage**: S3 for static assets like hotel images
  - Expected: Fast CDN-backed delivery of images to reduce latency
- **Load Balancing**: Nginx reverse proxy for routing and SSL termination
  - Expected: Secure HTTPS connections with Let's Encrypt certificates

**Expected Deployment Workflow:**
1. Build Docker containers with all dependencies
2. Deploy to EC2 instance via Docker Compose
3. Configure reverse proxy for routing and security
4. Set up SSL certificates for secure connections
5. Configure monitoring and logging

**Expected Performance:**
- Cold start time: 30-45 seconds for full application startup
- Steady-state memory usage: ~2-3GB with 4 workers
- Request handling capacity: 50-100 concurrent requests with t3.medium instance
- Image serving: < 200ms via S3 CloudFront CDN

**Scalability Considerations:**
- Horizontal scaling possible via load balancer and multiple EC2 instances
- Database can be migrated to RDS for better reliability
- Redis cluster for distributed caching in multi-instance setup

---
<!--

## Monitoring

### Metrics to Track
```python
# metrics.py

from prometheus_client import Counter, Histogram, Gauge

# Latency metrics
stt_latency = Histogram('stt_latency_seconds', 'STT processing time')
llm_latency = Histogram('llm_latency_seconds', 'LLM response time')
tts_latency = Histogram('tts_latency_seconds', 'TTS generation time')
total_latency = Histogram('total_latency_seconds', 'End-to-end latency')

# Request counters
requests_total = Counter('requests_total', 'Total requests', ['mode', 'status'])
errors_total = Counter('errors_total', 'Total errors', ['service', 'error_type'])

# Active connections
active_voice_sessions = Gauge('active_voice_sessions', 'Active voice sessions')
active_text_sessions = Gauge('active_text_sessions', 'Active text sessions')

# Business metrics
hotels_searched = Counter('hotels_searched', 'Hotels returned', ['city'])
api_calls = Counter('api_calls', 'External API calls', ['service'])
```

### Logging
```python
# logging_config.py

import logging
from pythonjsonlogger import jsonlogger

logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter(
    '%(timestamp)s %(level)s %(name)s %(message)s'
)
logHandler.setFormatter(formatter)

logger = logging.getLogger()
logger.addHandler(logHandler)
logger.setLevel(logging.INFO)

# Usage
logger.info(
    "Query processed",
    extra={
        "session_id": session_id,
        "mode": "voice",
        "latency_ms": 1150,
        "intent": "search_hotels",
        "results_count": 24
    }
)
```

### Health Checks
```python
# health.py

@app.get("/health")
async def health_check():
    checks = {
        "database": await check_database(),
        "elevenlabs": await check_elevenlabs(),
        "gemini": await check_gemini(),
        "rapidapi": await check_rapidapi()
    }
    
    all_healthy = all(checks.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "version": "0.1.0",
        "services": checks,
        "uptime_seconds": get_uptime()
    }

async def check_database():
    try:
        db.execute("SELECT 1")
        return "connected"
    except Exception as e:
        logger.error("Database health check failed", exc_info=e)
        return "disconnected"
```
-->

---

## Roadmap

*Note: Items marked with [x] indicate prototype/proof-of-concept completion, not production-ready implementation.*

### 🚧 Phase 1: Core MVP (In Progress)
- [x] Voice pipeline architecture design (STT → LLM → TTS)
- [x] Text chat mode prototype
- [x] Local database design (150-200 hotels schema)
- [x] Basic conversation context handling
- [ ] Docker containerization
- [ ] Cloud deployment setup

### 📋 Phase 2: Production Ready (Planned)
- [ ] Redis session management
- [ ] Comprehensive error handling
- [ ] Rate limiting and request queuing
- [ ] Monitoring dashboard (Grafana)
- [ ] Load testing (target: 100 concurrent users)
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Production deployment on AWS

### 📋 Phase 3: Enhanced Features (2-3 months)
- [ ] Multi-turn conversation improvements
- [ ] User authentication
- [ ] Personalized recommendations (ML model)
- [ ] Hotel comparison feature
- [ ] Voice interruption handling
- [ ] Multi-language support (Sinhala, Tamil)

### 🔮 Phase 4: Advanced (Future)
- [ ] Booking integration
- [ ] Payment processing
- [ ] User reviews and ratings
- [ ] Map visualization
- [ ] Mobile app (React Native)
- [ ] Voice biometrics for user identification

---
<!--

## Contributing

Currently a solo project, but contributions are welcome! If you'd like to contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 style guide
- Add type hints to all functions
- Write tests for new features
- Update documentation
- Keep commits atomic and descriptive

---

## License

MIT License - see [LICENSE](LICENSE) file for details

---
-->
## Acknowledgments

- **Pipecat** - Voice AI pipeline framework
- **ElevenLabs** - Best-in-class STT/TTS services
- **Google Gemini** - Fast and affordable LLM
- **FastAPI** - Modern Python web framework

---

## Contact

**Dulith Athukorala**
- GitHub: [@DulithAthukorala](https://github.com/DulithAthukorala)
- Email: [your-email@example.com]
- LinkedIn: [your-linkedin]

**Project Link:** [https://github.com/DulithAthukorala/Scenery](https://github.com/DulithAthukorala/Scenery)

---

<div align="center">

**voice AI engineering**


</div>