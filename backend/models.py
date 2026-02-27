from google import genai
from google.genai import types

from backend.config import GEMINI_API_KEY, GEMINI_MODEL

# Configure the API key
client = genai.Client(api_key=GEMINI_API_KEY)


def generate_text(
    prompt: str,
    max_output_tokens: int = 180,
    temperature: float = 0.4,
) -> str:
    """
    Simple Gemini text generation helper.
    """
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        ),
    )
    return response.text or ""
