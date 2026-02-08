from google import genai
from backend.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_NAME = "models/gemini-2.5-flash"

def generate_text(prompt: str) -> str:
    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )
    return resp.text or ""
