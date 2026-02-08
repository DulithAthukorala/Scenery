from fastapi import FastAPI
from backend.routers import health, voice

app = FastAPI(title="Scenery API")

app.include_router(health.router)
app.include_router(voice.router)
