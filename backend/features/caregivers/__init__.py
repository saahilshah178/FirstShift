"""caregivers feature.

Routes mounted at `/api/caregivers`:
- GET `/`              -> placeholder marker.
- GET `/list`          -> all caregivers (for the agency "Open caregiver view" picker).
- GET `/by-code/{code}` -> {caregiver, agency} by access code, or 404.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from db import get_db

router = APIRouter()


@router.get("/")
async def placeholder() -> dict:
    return {"feature": "caregivers", "status": "placeholder"}


def _public_caregiver(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "agency_id": doc.get("agency_id"),
        "name": doc.get("name"),
        "language": doc.get("language"),
        "hired_at": doc.get("hired_at"),
        "experience_note": doc.get("experience_note"),
        "cleared_skills": doc.get("cleared_skills") or [],
        "access_code": doc.get("access_code"),
    }


@router.get("/list")
async def list_caregivers():
    db = get_db()
    rows = await db.caregivers.find({}).to_list(length=200)
    agencies = await db.agencies.find({}, {"_id": 1, "name": 1}).to_list(length=100)
    a_by_id = {a["_id"]: a["name"] for a in agencies}
    out = []
    for c in rows:
        pc = _public_caregiver(c)
        pc["agency_name"] = a_by_id.get(pc["agency_id"], "unknown")
        out.append(pc)
    out.sort(key=lambda r: r["name"])
    return {"caregivers": out}


@router.get("/by-code/{code}")
async def by_code(code: str):
    db = get_db()
    code = code.strip().upper()
    doc = await db.caregivers.find_one({"access_code": code})
    if not doc:
        raise HTTPException(status_code=404, detail="caregiver not found")
    agency = await db.agencies.find_one({"_id": doc.get("agency_id")}) if doc.get("agency_id") else None
    return {
        "caregiver": _public_caregiver(doc),
        "agency": {"id": agency["_id"], "name": agency.get("name")} if agency else None,
    }
