from fastapi import FastAPI
from backend.routers import health, rapidapi_insights, localdb_insights, voice_ws_router

app = FastAPI(title="Scenery API")

app.include_router(health.router) # health check endpoint (GET /health)
app.include_router(rapidapi_insights.router) # rapidapi insights endpoint, takes search parameters + user request and returns LLM-ranked hotel insights
app.include_router(localdb_insights.router) # local db insights endpoint, takes exploratory search params and returns local DB hotel results
app.include_router(voice_ws_router.router) # voice websocket endpoint (POST /voice/stream)