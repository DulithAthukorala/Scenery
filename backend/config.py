import os
from pathlib import Path
from dotenv import load_dotenv

# Always load the .env that sits next to this file (backend/.env)
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ENV = os.getenv("ENV", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

if not GEMINI_API_KEY:
    raise RuntimeError(f"GEMINI_API_KEY is not set (loaded from: {ENV_PATH})")
