"""
Voice endpoint. This endpoint takes a prompt and returns a response from Gemini.
"""
from fastapi import APIRouter, HTTPException
from backend.models import generate_text

router = APIRouter(prefix="/voice", tags=["voice"])

@router.post("/ask")
def ask_llm(prompt: str):
    try:
        text = generate_text(prompt)
        if not text:
            raise ValueError("Empty response from Gemini")
        return {"response": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))
