import logging

from google import genai
from google.genai import types
from groq import Groq

from backend.config import GEMINI_API_KEY, GEMINI_MODEL, GROQ_API_KEY, GROQ_MODEL

log = logging.getLogger(__name__)

# ---------- clients ----------
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Circuit breaker: if Gemini fails once, skip it for remaining calls
_gemini_is_down = False


def _call_gemini(prompt: str, max_output_tokens: int, temperature: float) -> str:
    """Primary LLM — Google Gemini."""
    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        ),
    )
    return response.text or ""


def _call_groq(prompt: str, max_output_tokens: int, temperature: float) -> str:
    """Fallback LLM — Groq (LLaMA)."""
    if groq_client is None:
        raise RuntimeError("GROQ_API_KEY is not configured")
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_output_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


def generate_text(
    prompt: str,
    max_output_tokens: int = 1024,
    temperature: float = 0.4,
) -> str:
    """
    Try Gemini first; if it fails and Groq is configured, fall back to Groq.
    Once Gemini fails, all subsequent calls skip straight to Groq (circuit breaker).
    """
    global _gemini_is_down
    
    # If Gemini already failed, skip straight to Groq
    if _gemini_is_down:
        if groq_client is None:
            raise RuntimeError("Gemini is down and Groq is not configured")
        return _call_groq(prompt, max_output_tokens, temperature)
    
    # Try Gemini first
    try:
        return _call_gemini(prompt, max_output_tokens, temperature)
    except Exception as e:
        log.warning("Gemini failed (%s), switching to Groq for all subsequent calls", e)
        _gemini_is_down = True
        if groq_client is None:
            raise  # no fallback available, re-raise original error
        return _call_groq(prompt, max_output_tokens, temperature)
