"""questions feature.

Routes mounted at `/api/questions`:
- GET  `/`                           placeholder marker (Phase-1 shape, preserved).
- GET  `/list`                       preserved shape (all questions, raw).
- GET  `/inbox`                      agency inbox: waiting + answered.
- POST `/ask`                        caregiver convenience: {caregiver_id, text}.
- POST `/{question_id}/answer`       care manager delivers an answer.
- POST `/transcribe`                 multipart audio → {media_id, transcript}.
- GET  `/policies`                   list seeded policies (for UI reference).
"""
from __future__ import annotations

from fastapi import APIRouter

from db import get_db

from .routes import router as _inner_router

router = APIRouter()


@router.get("/")
async def placeholder() -> dict:
    return {"feature": "questions", "status": "placeholder"}


@router.get("/list")
async def list_questions():
    db = get_db()
    rows = await db.questions.find({}, {"_id": 0}).to_list(length=200)
    return {"questions": rows}


router.include_router(_inner_router)
