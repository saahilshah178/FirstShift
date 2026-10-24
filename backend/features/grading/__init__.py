"""grading feature.

Routes mounted at `/api/grading`:
- GET  `/`                           -> placeholder marker.
- POST `/clips`                      -> upload + transcode + attempt create (grading background task starts).
- GET  `/attempts`                   -> list; keeps the Phase-2 shape, adds optional filters.
- GET  `/attempts/{id}`              -> poll one attempt (full doc).
- POST `/attempts/{id}/regrade`      -> re-run grading on the stored clip.
- GET  `/queue`                      -> {ready_to_sign, needs_practice} for Sign-off view (Stage 5).
- POST `/attempts/{id}/signoff`      -> approve / send_back (Stage 5).
- GET  `/competency`                 -> keeps the Phase-2 shape.
- GET  `/competency/{caregiver_id}`  -> per-caregiver competency file (Stage 5).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from db import get_db

from .background import enqueue_grade, mark_stale_grading
from .ingest import ingest_clip
from .seed import schedule_startup_seed

logger = logging.getLogger("firstshift.grading")

router = APIRouter()

# Fire-and-forget: ensure the Glove-removal skill exists, and sweep
# any stale `grading` attempts that outlived the last process. Both
# are safe at module import time because the server imports features
# inside its async startup handler.
schedule_startup_seed()


async def _startup_tasks() -> None:
    try:
        n = await mark_stale_grading()
        if n:
            logger.info("marked %d stale attempts as grading_error", n)
    except Exception:  # noqa: BLE001
        logger.exception("stale-grading sweep failed")


try:
    asyncio.get_running_loop().create_task(_startup_tasks())
except RuntimeError:
    pass


# ---- placeholder ----
@router.get("/")
async def placeholder() -> dict:
    return {"feature": "grading", "status": "placeholder"}


# ---- clip upload ----
@router.post("/clips")
async def upload_clip(
    file: UploadFile = File(...),
    skill_id: str = Form(...),
    caregiver_id: str = Form(...),
) -> dict:
    result = await ingest_clip(
        file=file, skill_id=skill_id, caregiver_id=caregiver_id
    )
    enqueue_grade(
        result["attempt_id"], skill_id, caregiver_id, result["clip_id"]
    )
    return result


# ---- attempts list (keeps Phase-2 shape; adds additive fields + filters) ----
_READ_STATUSES = {"grading", "ready_to_sign", "needs_practice", "retake_required", "grading_error"}


async def _check_single_stale(attempt: dict) -> None:
    """If one attempt is in `grading` and older than 10 min, flip it inline."""
    from datetime import timedelta
    if attempt.get("status") != "grading":
        return
    created = attempt.get("created_at")
    if not created:
        return
    try:
        created_dt = datetime.fromisoformat(created)
    except ValueError:
        return
    if datetime.now(timezone.utc) - created_dt > timedelta(minutes=10):
        db = get_db()
        await db.attempts.update_one(
            {"_id": attempt["_id"]},
            {"$set": {"status": "grading_error", "error": "grading timed out"}},
        )
        attempt["status"] = "grading_error"
        attempt["error"] = "grading timed out"


@router.get("/attempts")
async def list_attempts(
    caregiver_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    db = get_db()
    q: dict = {}
    if caregiver_id:
        q["caregiver_id"] = caregiver_id
    if status:
        if status not in _READ_STATUSES:
            raise HTTPException(status_code=422, detail=f"unknown status: {status}")
        q["status"] = status
    attempts = await db.attempts.find(q).sort("created_at", -1).to_list(length=200)

    # Sweep stale "grading" rows inline.
    for a in attempts:
        await _check_single_stale(a)

    caregiver_ids = {a["caregiver_id"] for a in attempts}
    skill_ids = {a["skill_id"] for a in attempts}
    caregivers = await db.caregivers.find({"_id": {"$in": list(caregiver_ids)}}).to_list(length=200)
    skills = await db.skills.find({"_id": {"$in": list(skill_ids)}}).to_list(length=100)
    c_by_id = {c["_id"]: c for c in caregivers}
    s_by_id = {s["_id"]: s for s in skills}
    return {
        "attempts": [
            {
                # Phase-2 fields — DO NOT change shape:
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
                # Additive Phase-3 fields:
                "status": a.get("status"),
                "verdict": a.get("verdict"),
                "score": a.get("score"),
                "runs_used": a.get("runs_used", 0),
                "graded_once": a.get("graded_once", False),
                "reviewed": a.get("reviewed", False),
            }
            for a in attempts
        ]
    }


# ---- single-attempt polling ----
def _public_attempt(doc: dict, skill_title: str | None, caregiver_name: str | None) -> dict:
    return {
        "id": doc["_id"],
        "caregiver_id": doc["caregiver_id"],
        "caregiver_name": caregiver_name,
        "skill_id": doc["skill_id"],
        "skill_title": skill_title,
        "clip_id": doc.get("clip_id"),
        "duration": doc.get("duration"),
        "status": doc.get("status"),
        "verdict": doc.get("verdict"),
        "overall": doc.get("overall"),
        "score": doc.get("score"),
        "message_for_caregiver": doc.get("message_for_caregiver", ""),
        "runs_used": doc.get("runs_used", 0),
        "graded_once": doc.get("graded_once", False),
        "reviewed": doc.get("reviewed", False),
        "error": doc.get("error"),
        "created_at": doc.get("created_at"),
        "graded_at": doc.get("graded_at"),
        "checks": [
            {
                "id": c["id"],
                "description": c.get("description", ""),
                "result": c.get("result"),
                "time": c.get("time"),
                "seen": c.get("seen"),
                "safety_critical": bool(c.get("safety_critical", False)),
                "note": c.get("note", ""),
            }
            for c in doc.get("checks", [])
        ],
    }


@router.get("/attempts/{attempt_id}")
async def get_attempt(attempt_id: str):
    db = get_db()
    a = await db.attempts.find_one({"_id": attempt_id})
    if not a:
        raise HTTPException(status_code=404, detail="attempt not found")
    await _check_single_stale(a)
    skill = await db.skills.find_one({"_id": a["skill_id"]}, {"title": 1})
    caregiver = await db.caregivers.find_one({"_id": a["caregiver_id"]}, {"name": 1})
    # Fetch any send-back note from signoffs.
    signoff = await db.signoffs.find_one(
        {"attempt_id": attempt_id}, sort=[("at", -1)],
    )
    out = _public_attempt(
        a, (skill or {}).get("title"), (caregiver or {}).get("name"),
    )
    if signoff:
        out["signoff"] = {
            "decision": signoff.get("decision"),
            "signer": signoff.get("signer"),
            "signer_role": signoff.get("signer_role", ""),
            "note": signoff.get("note", ""),
            "override": bool(signoff.get("override", False)),
            "at": signoff.get("at"),
        }
    return out


# ---- regrade ----
@router.post("/attempts/{attempt_id}/regrade")
async def regrade_attempt(attempt_id: str):
    db = get_db()
    a = await db.attempts.find_one({"_id": attempt_id})
    if not a:
        raise HTTPException(status_code=404, detail="attempt not found")
    if a.get("reviewed"):
        raise HTTPException(status_code=409, detail="attempt already reviewed")
    await db.attempts.update_one(
        {"_id": attempt_id},
        {"$set": {
            "status": "grading",
            "error": None,
            "overall": None,
            "verdict": None,
            "checks": [],
            "runs_used": 0,
            "graded_once": False,
            "message_for_caregiver": "",
        }},
    )
    enqueue_grade(
        attempt_id, a["skill_id"], a["caregiver_id"], a["clip_id"]
    )
    return {"attempt_id": attempt_id, "status": "grading"}


# ---- Phase-2 competency (shape frozen) ----
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


# Stage-5 endpoints (queue, signoff, per-caregiver competency) are
# registered from `.routes_signoff` to keep this module readable.
from .routes_signoff import attach as _attach_signoff_routes  # noqa: E402

_attach_signoff_routes(router)
