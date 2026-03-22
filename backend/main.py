import warnings
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.routers import health, rapidapi_insights, localdb_insights, voice, chat, voice_room

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


# signore pydantic warnings about field names that match BaseModel attributes by google genai library
warnings.filterwarnings("ignore", message="Field name .* shadows an attribute in parent")
app = FastAPI(title="Scenery API")

# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
    expose_headers=["X-Total-Ms", "X-Decision-Ms", "X-Action", "X-Session-Id"],
)

app.include_router(health.router)
app.include_router(rapidapi_insights.router)
app.include_router(localdb_insights.router)
app.include_router(voice.router)
app.include_router(voice_room.router)
app.include_router(chat.router)

# Serve the frontend so pages open from http://localhost:8000/voice.html etc.
# This must come LAST — all API routers are registered above.
# file:// never persists mic permissions; localhost does.
if FRONTEND_DIR.is_dir():
    @app.get("/")
    async def root():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/{page}.html")
    async def serve_page(page: str):
        f = FRONTEND_DIR / f"{page}.html"
        return FileResponse(f) if f.is_file() else FileResponse(FRONTEND_DIR / "index.html")

    # Serve all other static assets (CSS, JS, images) — registered last
    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")