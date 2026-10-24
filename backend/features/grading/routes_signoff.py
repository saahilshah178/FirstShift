"""Stage-5 signoff + competency routes.

Attached via `attach(router)` from `features/grading/__init__.py`.

Routes added:
- GET  /api/grading/queue
- POST /api/grading/attempts/{id}/signoff
- GET  /api/grading/competency/{caregiver_id}
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db import get_db

logger = logging.getLogger("firstshift.grading.signoff")


# ---- queue ----
SIGNABLE_STATUSES = ("ready_to_sign", "needs_practice")


async def _queue() -> dict:
    db = get_db()
    attempts = await db.attempts.find({
        "status": {"$in": list(SIGNABLE_STATUSES)},
        "reviewed": {"$ne": True},
    }).sort("created_at", -1).to_list(length=200)
    caregiver_ids = {a["caregiver_id"] for a in attempts}
    skill_ids = {a["skill_id"] for a in attempts}
    caregivers = await db.caregivers.find({"_id": {"$in": list(caregiver_ids)}}).to_list(length=200)
    skills = await db.skills.find({"_id": {"$in": list(skill_ids)}}).to_list(length=100)
    c_by_id = {c["_id"]: c for c in caregivers}
    s_by_id = {s["_id"]: s for s in skills}

    def _row(a: dict) -> dict:
        return {
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
            "verdict": a.get("verdict"),
            "score": a.get("score"),
            "runs_used": a.get("runs_used", 0),
            "graded_once": a.get("graded_once", False),
            "created_at": a.get("created_at"),
            "message_for_caregiver": a.get("message_for_caregiver", ""),
        }

    ready = [_row(a) for a in attempts if a.get("status") == "ready_to_sign"]
    practice = [_row(a) for a in attempts if a.get("status") == "needs_practice"]
    return {"ready_to_sign": ready, "needs_practice": practice}


# ---- signoff body model ----
class SignoffBody(BaseModel):
    decision: Literal["approve", "send_back"]
    signer: str = Field(..., min_length=1, max_length=80)
    signer_role: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=2000)


# ---- signoff action ----
async def _signoff(attempt_id: str, body: SignoffBody) -> dict:
    db = get_db()
    attempt = await db.attempts.find_one({"_id": attempt_id})
    if not attempt:
        raise HTTPException(status_code=404, detail="attempt not found")

    if attempt.get("reviewed"):
        raise HTTPException(status_code=409, detail="attempt already reviewed")

    if attempt.get("status") not in SIGNABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"attempt status is {attempt.get('status')!r}; not signable",
        )

    # Must be the latest attempt for this caregiver+skill.
    newer = await db.attempts.find_one(
        {
            "caregiver_id": attempt["caregiver_id"],
            "skill_id": attempt["skill_id"],
            "created_at": {"$gt": attempt.get("created_at", "")},
        },
        sort=[("created_at", -1)],
    )
    if newer:
        raise HTTPException(
            status_code=409,
            detail="a newer attempt exists for this caregiver+skill",
        )

    override = False
    now = datetime.now(timezone.utc).isoformat()

    if body.decision == "approve":
        # Any failed check means the auto verdict was "retry" — override allowed with note.
        has_fail = any(c.get("result") == "fail" for c in attempt.get("checks", []))
        if attempt.get("verdict") == "retry" or has_fail:
            if not body.note.strip():
                raise HTTPException(
                    status_code=422,
                    detail="note required when overriding a failed/retry verdict",
                )
            override = True
        # Add skill to caregiver.cleared_skills via $addToSet (idempotent).
        add_result = await db.caregivers.update_one(
            {"_id": attempt["caregiver_id"]},
            {"$addToSet": {"cleared_skills": attempt["skill_id"]}},
        )
        # Channel hook: notify the caregiver ONLY when the $addToSet actually
        # added the skill (not re-adds). Fire-and-forget — a chat failure must
        # not block sign-off persistence.
        if add_result.modified_count:
            try:
                from services.channel_service import send_message_async
                skill_doc = await db.skills.find_one({"_id": attempt["skill_id"]})
                caregiver_doc = await db.caregivers.find_one({"_id": attempt["caregiver_id"]})
                lang = (caregiver_doc or {}).get("language") or "en"
                skill_title = (skill_doc or {}).get("title") or "the skill"
                if lang in ("es", "tl"):
                    t = ((skill_doc or {}).get("translations") or {}).get(lang) or {}
                    if t.get("title"):
                        skill_title = t["title"]
                cleared_tmpl = {
                    "en": "You're cleared for {title}.",
                    "es": "Estás aprobada para {title}.",
                    "tl": "Pasado ka na sa {title}.",
                }[lang if lang in ("es", "tl") else "en"]
                await send_message_async(
                    attempt["caregiver_id"],
                    cleared_tmpl.format(title=skill_title),
                )
            except Exception:  # noqa: BLE001
                logger.exception("channel hook on signoff approve failed")
    else:  # send_back
        if not body.note.strip():
            raise HTTPException(
                status_code=422,
                detail="note required when sending back",
            )

    signoff_doc = {
        "_id": uuid.uuid4().hex,
        "attempt_id": attempt_id,
        "caregiver_id": attempt["caregiver_id"],
        "skill_id": attempt["skill_id"],
        "signer": body.signer.strip(),
        "signer_role": body.signer_role.strip(),
        "decision": body.decision,
        "note": body.note.strip(),
        "override": override,
        "at": now,
    }
    await db.signoffs.insert_one(signoff_doc)
    await db.attempts.update_one(
        {"_id": attempt_id}, {"$set": {"reviewed": True}},
    )
    return {
        "attempt_id": attempt_id,
        "decision": body.decision,
        "override": override,
        "signoff_id": signoff_doc["_id"],
    }


# ---- per-caregiver competency file ----
async def _competency_for(caregiver_id: str) -> dict:
    db = get_db()
    caregiver = await db.caregivers.find_one({"_id": caregiver_id})
    if not caregiver:
        raise HTTPException(status_code=404, detail="caregiver not found")

    skills = await db.skills.find({}).to_list(length=100)
    cleared = set(caregiver.get("cleared_skills") or [])

    # Gather all attempts + signoffs for this caregiver.
    attempts = await db.attempts.find({"caregiver_id": caregiver_id}).sort("created_at", -1).to_list(length=500)
    signoffs = await db.signoffs.find({"caregiver_id": caregiver_id}).to_list(length=500)
    signoff_by_attempt = {s["attempt_id"]: s for s in signoffs}

    rows: list[dict] = []
    for skill in skills:
        sid = skill["_id"]
        skill_attempts = [a for a in attempts if a["skill_id"] == sid]
        latest = skill_attempts[0] if skill_attempts else None
        if sid in cleared:
            status = "cleared"
        elif latest:
            status = "not_cleared"
        else:
            status = "not_attempted"

        def _attempt_summary(a: dict) -> dict:
            s = signoff_by_attempt.get(a["_id"])
            return {
                "attempt_id": a["_id"],
                "overall": a.get("overall"),
                "verdict": a.get("verdict"),
                "status": a.get("status"),
                "score": a.get("score"),
                "date": a.get("created_at"),
                "clip_id": a.get("clip_id"),
                "runs_used": a.get("runs_used", 0),
                "graded_once": a.get("graded_once", False),
                "signer": (s or {}).get("signer"),
                "signer_role": (s or {}).get("signer_role"),
                "decision": (s or {}).get("decision"),
                "override": bool((s or {}).get("override", False)),
                "note": (s or {}).get("note"),
            }

        rows.append({
            "skill": {"id": sid, "title": skill.get("title")},
            "status": status,
            "latest": _attempt_summary(latest) if latest else None,
            "history": [_attempt_summary(a) for a in skill_attempts],
        })

    rows.sort(key=lambda r: r["skill"]["title"])
    return {
        "caregiver": {
            "id": caregiver["_id"],
            "name": caregiver.get("name"),
            "language": caregiver.get("language"),
            "agency_id": caregiver.get("agency_id"),
        },
        "skills": rows,
    }


def attach(router: APIRouter) -> None:
    @router.get("/queue")
    async def get_queue():
        return await _queue()

    @router.post("/attempts/{attempt_id}/signoff")
    async def post_signoff(attempt_id: str, body: SignoffBody):
        return await _signoff(attempt_id, body)

    @router.get("/competency/{caregiver_id}")
    async def get_competency_for(caregiver_id: str):
        return await _competency_for(caregiver_id)

    @router.get("/skill/{skill_id}")
    async def get_skill(skill_id: str):
        """Full skill doc (steps + translations) for the Practice UI."""
        db = get_db()
        s = await db.skills.find_one({"_id": skill_id})
        if not s:
            raise HTTPException(status_code=404, detail="skill not found")
        return {
            "skill": {
                "id": s["_id"],
                "title": s.get("title"),
                "steps": s.get("steps", []),
                "checks": s.get("checks", []),
                "quiz": s.get("quiz", []),
                "translations": s.get("translations", {}),
            }
        }
