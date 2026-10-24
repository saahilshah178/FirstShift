"""questions feature — placeholder for Phase 1."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def placeholder() -> dict:
    return {"feature": "questions", "status": "placeholder"}
