"""lessons feature.

Routes mounted at `/api/lessons`:
- GET `/`               -> placeholder marker.
- GET `/skills`         -> all skills (id, title, step_count, check_count).
- GET `/caregiver/:id`  -> cleared + remaining skills for a caregiver.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from db import get_db

router = APIRouter()


@router.get("/")
async def placeholder() -> dict:
    return {"feature": "lessons", "status": "placeholder"}


@router.get("/skills")
async def list_skills():
    db = get_db()
    skills = await db.skills.find({}).to_list(length=100)
    return {
        "skills": [
            {
                "id": s["_id"],
                "title": s.get("title"),
                "step_count": len(s.get("steps", [])),
                "check_count": len(s.get("checks", [])),
            }
            for s in skills
        ]
    }


@router.get("/caregiver/{caregiver_id}")
async def caregiver_lessons(caregiver_id: str):
    db = get_db()
    caregiver = await db.caregivers.find_one({"_id": caregiver_id})
    if not caregiver:
        raise HTTPException(status_code=404, detail="caregiver not found")
    all_skills = await db.skills.find({}).to_list(length=100)
    cleared = set(caregiver.get("cleared_skills") or [])
    return {
        "caregiver": {"id": caregiver["_id"], "name": caregiver.get("name")},
        "cleared": [
            {"id": s["_id"], "title": s["title"], "step_count": len(s.get("steps", []))}
            for s in all_skills
            if s["_id"] in cleared
        ],
        "remaining": [
            {"id": s["_id"], "title": s["title"], "step_count": len(s.get("steps", []))}
            for s in all_skills
            if s["_id"] not in cleared
        ],
    }
