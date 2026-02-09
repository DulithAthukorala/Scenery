import os
from pathlib import Path
from dotenv import load_dotenv

# Always load the .env that sits next to this file (backend/.env)
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True) # override=True (If a variable already exists, replace it

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ENV = os.getenv("ENV", "development") # what environment we're running in (development, production, etc.)
LOG_LEVEL = os.getenv("LOG_LEVEL", "info") # how noisy the logs should be (debug, info, warning, error, critical)

if not GEMINI_API_KEY:
    raise RuntimeError(f"GEMINI_API_KEY is not set (loaded from: {ENV_PATH})")


RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")

if not RAPIDAPI_KEY or not RAPIDAPI_HOST:
    raise RuntimeError(f"RapidAPI creds missing. Loaded from: {ENV_PATH}")



