from fastapi import FastAPI
from backend.routers import health, voice, tripadvisor

app = FastAPI(title="Scenery API")

app.include_router(health.router) # health check endpoint (GET /health)
app.include_router(voice.router) # voice endpoint (POST /voice/ask) that takes a prompt and returns a response from Gemini
app.include_router(tripadvisor.router) # tripadvisor endpoint (GET /tripadvisor/hotels/search) that takes search parameters and returns hotel data from TripAdvisor
