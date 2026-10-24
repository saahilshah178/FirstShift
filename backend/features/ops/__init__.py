"""ops feature — agency ops endpoints.

Routes mounted at `/api/ops`:
- GET `/`          -> placeholder marker.
- GET `/caregivers` -> list caregivers (name, language, hired_at, agency_id).
                       Optional `?sort=hired_at_desc` for the "New hires" view.
- GET `/clients`   -> list clients with `required_skills` resolved to titles.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from db import get_db

router = APIRouter()


@router.get("/")
async def placeholder() -> dict:
    return {"feature": "ops", "status": "placeholder"}


def _projection_caregiver() -> dict:
    return {
        "_id": 0,
        "id": "$_id",
        "agency_id": 1,
        "name": 1,
        "language": 1,
        "hired_at": 1,
        "experience_note": 1,
        "cleared_skills": 1,
        "access_code": 1,
    }


@router.get("/caregivers")
async def list_caregivers(sort: str | None = Query(default=None)):
    db = get_db()
    cursor = db.caregivers.aggregate([
        {"$project": _projection_caregiver()},
    ])
    rows = await cursor.to_list(length=1000)
    if sort == "hired_at_desc":
        rows.sort(key=lambda r: r.get("hired_at", ""), reverse=True)
    else:
        rows.sort(key=lambda r: r.get("name", ""))
    return {"caregivers": rows}


@router.get("/clients")
async def list_clients():
    db = get_db()
    clients = await db.clients.find({}, {"_id": 1, "agency_id": 1, "name": 1, "required_skills": 1}).to_list(length=1000)
    skills = await db.skills.find({}, {"_id": 1, "title": 1}).to_list(length=1000)
    title_by_id = {s["_id"]: s["title"] for s in skills}
    result = []
    for c in clients:
        result.append({
            "id": c["_id"],
            "agency_id": c.get("agency_id"),
            "name": c.get("name"),
            "required_skills": [
                {"id": sid, "title": title_by_id.get(sid, "unknown")}
                for sid in c.get("required_skills", [])
            ],
        })
    result.sort(key=lambda r: r["name"])
    return {"clients": result}
