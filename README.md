# Scenery 🏝️

> **🚧 Work in Progress 🚧**

A voice-first hotel recommendation agent for Sri Lanka that prioritizes speed, trust, and natural interaction.

---

## 🎯 Project Goal

Build a **production-grade voice assistant** that helps users discover hotels in Sri Lanka through natural conversation, with:

- **Near-instant responses** (sub-1 second for recommendations)
- **Honest AI behavior** (no hallucinated prices)
- **Smart tradeoffs** (fast local search + optional live price checks with user consent)

---

## 🎤 What is Scenery?

Scenery is a latency-aware recommendation agent that uses a **two-speed intelligence system**:

### ⚡ Fast Path (Default)
Find hotels instantly based on vibe, location, or budget using local vector search
- *"Beach hotels in Mirissa"* → **responds in < 1 second**

### 🔍 Slow Path (User-Approved)
Check live prices only when explicitly requested with user consent
- *"What's the exact price?"* → **asks permission first, then fetches**

---

## 🏗️ Technical Scope

### Core Stack
- **Frontend:** Next.js (TypeScript) with voice UI
- **Backend:** FastAPI (Python) with AI pipeline (STT → Intent → Retrieval → Response → TTS)
- **Search:** FAISS vector embeddings for semantic matching
- **Infrastructure:** AWS EC2 (always-on for predictable latency)

### Key Components
1. Voice interface (push-to-talk, audio playback)
2. Hotel dataset (30-100 curated Sri Lankan hotels)
3. Vibe-based vector search
4. Optional live price checking (with consent)

---

## 🎯 Why This Matters

**Most voice assistants fail at two things:**
1. **Speed** - they feel laggy
2. **Trust** - they hallucinate information

**Scenery is designed around both:**
- Instant recommendations using local data
- Explicit consent before slow operations
- No fake prices, ever

---

## 📊 Current Status

### ✅ Completed
- [x] Product vision and architecture defined
- [x] Technical scope documented

### 🚧 In Progress
- [ ] Voice pipeline implementation (STT, LLM, TTS)
- [ ] Hotel dataset curation and embedding
- [ ] Vector search setup (FAISS)
- [ ] Frontend UI development
- [ ] AWS deployment

---

## 🚀 Quick Start

*Coming soon - watch this space!*

```bash
# Frontend
cd frontend && npm install && npm run dev

# Backend
cd backend && pip install -r requirements.txt && python main.py
```

---

## 📖 Learn More

This project demonstrates:
- **Latency-aware AI architecture** with explicit speed/accuracy tradeoffs
- **Trust-first design** (user consent for slow operations)
- **Production engineering** (real cloud deployment, not localhost)
- **Voice-first UX** optimized for mobile and travel use cases

---

## 👤 Author

**Dulith Athukorala**  
GitHub: [@DulithAthukorala](https://github.com/DulithAthukorala)

---

**Made with ❤️ in Sri Lanka** 🇱🇰
