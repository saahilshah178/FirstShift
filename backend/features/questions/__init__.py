"""questions feature.

Routes mounted at `/api/questions`:
- GET `/`      -> placeholder marker.
- GET `/list`  -> all stored questions (currently empty — reserved for later phases).
"""
from __future__ import annotations

from fastapi import APIRouter

from db import get_db

router = APIRouter()


@router.get("/")
async def placeholder() -> dict:
    return {"feature": "questions", "status": "placeholder"}


@router.get("/list")
async def list_questions():
    db = get_db()
    rows = await db.questions.find({}, {"_id": 0}).to_list(length=200)
    return {"questions": rows}
