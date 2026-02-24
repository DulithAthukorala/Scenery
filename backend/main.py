import warnings
from fastapi import FastAPI
from backend.routers import health, rapidapi_insights, localdb_insights, voice, chat


# signore pydantic warnings about field names that match BaseModel attributes by google genai library
warnings.filterwarnings("ignore", message="Field name .* shadows an attribute in parent")
app = FastAPI(title="Scenery API")

app.include_router(health.router) # health check endpoint (GET /health)
app.include_router(rapidapi_insights.router) # rapidapi insights endpoint, takes search parameters + user request and returns LLM-ranked hotel insights
app.include_router(localdb_insights.router) # local db insights endpoint, takes exploratory search params and returns local DB hotel results
app.include_router(voice.router) # voice websocket endpoint (WS /voice/stream)
app.include_router(chat.router) # text endpoint (POST /chat)