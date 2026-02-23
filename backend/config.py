import os
from pathlib import Path
from dotenv import load_dotenv

# Always load the .env that sits next to this file (backend/.env)
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True) # override=True (If a variable already exists, replace it

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")
ENV = os.getenv("ENV", "development") # what environment we're running in (development, production, etc.)
LOG_LEVEL = os.getenv("LOG_LEVEL", "info") # how noisy the logs should be (debug, info, warning, error, critical)

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "")
ELEVEN_STT_MODEL_ID = os.getenv("ELEVEN_STT_MODEL_ID", "scribe_v2_realtime")
ELEVEN_STT_SAMPLE_RATE = int(os.getenv("ELEVEN_STT_SAMPLE_RATE", "16000"))

if not GEMINI_API_KEY:
    raise RuntimeError(f"GEMINI_API_KEY is not set (loaded from: {ENV_PATH})")

if not RAPIDAPI_KEY or not RAPIDAPI_HOST:
    raise RuntimeError(f"RapidAPI creds missing. Loaded from: {ENV_PATH}")



