from fastapi import APIRouter
from backend.models import model

router = APIRouter(prefix="/voice", tags=["voice"])

@router.post("/ask")
def ask_llm(prompt: str):
    response = model.generate_content(prompt)
    return {
        "response": response.text
    }
