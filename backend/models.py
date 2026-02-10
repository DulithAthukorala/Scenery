from google import genai

from backend.config import GEMINI_API_KEY, GEMINI_MODEL

# Create ONE client for the whole app
client = genai.Client(api_key=GEMINI_API_KEY)


def generate_text(prompt: str) -> str:
    """
    Simple Gemini text generation helper.
    """
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return response.text or ""
