"""grading feature.

Routes mounted at `/api/grading`:
- GET `/`           -> placeholder marker.
- GET `/attempts`   -> recent attempts enriched with caregiver + skill name.
- GET `/competency` -> caregivers grouped by cleared-skill count.
"""
from __future__ import annotations

from fastapi import APIRouter

from db import get_db

router = APIRouter()


@router.get("/")
async def placeholder() -> dict:
    return {"feature": "grading", "status": "placeholder"}


@router.get("/attempts")
async def list_attempts():
    db = get_db()
    attempts = await db.attempts.find({}).sort("created_at", -1).to_list(length=100)
    caregiver_ids = {a["caregiver_id"] for a in attempts}
    skill_ids = {a["skill_id"] for a in attempts}
    caregivers = await db.caregivers.find({"_id": {"$in": list(caregiver_ids)}}).to_list(length=100)
    skills = await db.skills.find({"_id": {"$in": list(skill_ids)}}).to_list(length=100)
    c_by_id = {c["_id"]: c for c in caregivers}
    s_by_id = {s["_id"]: s for s in skills}
    return {
        "attempts": [
            {
                "id": a["_id"],
                "caregiver": {
                    "id": a["caregiver_id"],
                    "name": c_by_id.get(a["caregiver_id"], {}).get("name", "unknown"),
                },
                "skill": {
                    "id": a["skill_id"],
                    "title": s_by_id.get(a["skill_id"], {}).get("title", "unknown"),
                },
                "overall": a.get("overall"),
                "clip_id": a.get("clip_id"),
                "created_at": a.get("created_at"),
                "check_results": [
                    {"id": c["id"], "result": c.get("result"), "seen": c.get("seen")}
                    for c in a.get("checks", [])
                ],
            }
            for a in attempts
        ]
    }


@router.get("/competency")
async def competency_files():
    db = get_db()
    caregivers = await db.caregivers.find({}).to_list(length=200)
    skills = await db.skills.find({}, {"_id": 1, "title": 1}).to_list(length=100)
    title_by_id = {s["_id"]: s["title"] for s in skills}
    rows = []
    for c in caregivers:
        cleared = c.get("cleared_skills") or []
        rows.append({
            "id": c["_id"],
            "name": c.get("name"),
            "cleared_count": len(cleared),
            "cleared": [{"id": sid, "title": title_by_id.get(sid, "unknown")} for sid in cleared],
        })
    rows.sort(key=lambda r: (-r["cleared_count"], r["name"]))
    return {"caregivers": rows, "total_skills": len(skills)}
