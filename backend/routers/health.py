"""
Health check endpoint. This is a simple endpoint that can be used to check if the server is running and responsive.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])

@router.get("")
def health_check():
    return {"status": "ok"}
