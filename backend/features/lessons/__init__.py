"""lessons feature.

Routes mounted at `/api/lessons`:

Preserved from Phase 2 (shapes byte-identical):
- `GET  /`                           -> placeholder marker.
- `GET  /skills`                     -> all skills (id, title, step_count, check_count).
- `GET  /caregiver/:id`              -> cleared + remaining skills for a caregiver.

Added by `lessons/record` branch:
- `POST /uploads`                                   init chunked upload
- `PUT  /uploads/{upload_id}/chunks/{index}`        raw-bytes chunk
- `POST /uploads/{upload_id}/complete`              assemble + create job
- `GET  /jobs`                                      list in-progress + ready + failed jobs
- `GET  /jobs/{job_id}`                             single job detail
- `POST /jobs/{job_id}/retry`
- `PUT  /jobs/{job_id}/draft`
- `POST /jobs/{job_id}/steps/{n}/frame`
- `POST /jobs/{job_id}/publish`
- `POST /skills/{skill_id}/edit`
- `GET  /skills/{skill_id}`                         full skill doc
- `PUT  /skills/{skill_id}/translations/{es|tl}`
- `POST /skills/{skill_id}/translations/{es|tl}/review`
- `POST /skills/{skill_id}/translations/retry`
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query

from db import get_db

from .jobs import router as _jobs_router
from .runner import sweep_stale_jobs
from .skills_routes import router as _skills_router
from .uploads import router as _uploads_router

logger = logging.getLogger("firstshift.lessons")

router = APIRouter()


@router.get("/")
async def placeholder() -> dict:
    return {"feature": "lessons", "status": "placeholder"}


@router.get("/skills")
async def list_skills(include_archived: bool = Query(False)):
    db = get_db()
    query: dict = {} if include_archived else {"archived": {"$ne": True}}
    skills = await db.skills.find(query).to_list(length=200)
    return {
        "skills": [
            {
                "id": s["_id"],
                "title": s.get("title"),
                "step_count": len(s.get("steps", [])),
                "check_count": len(s.get("checks", [])),
                "archived": bool(s.get("archived", False)),
            }
            for s in skills
        ]
    }


@router.get("/caregiver/{caregiver_id}")
async def caregiver_lessons(caregiver_id: str):
    """Caregiver's lesson list with status chips.

    Stage 2 — Items F + G: every skill (cleared + remaining) carries a
    `status` value drawn from the SAME source of truth agency uses
    (`cleared_skills`, `attempts`, `conversations`). The caregiver's
    Lessons tab and Practice tab both render these chips with no extra
    plumbing on the frontend side.

    Status values:
      - "cleared"               — skill in `caregiver.cleared_skills`.
      - "awaiting_signoff"      — caregiver has an attempt in
                                   `ready_to_sign`/`needs_practice` for
                                   this skill, not yet `reviewed`.
      - "practice_video_next"   — conversation.state == `awaiting_video`
                                   AND conv.skill_id == this skill
                                   (walked the steps + quiz, no clip yet).
      - "in_progress"           — conversation.state ∈ {`in_lesson`,`quiz`}
                                   AND conv.skill_id == this skill.
      - "todo" or null          — none of the above (no chip in the UI).
    """
    db = get_db()
    caregiver = await db.caregivers.find_one({"_id": caregiver_id})
    if not caregiver:
        raise HTTPException(status_code=404, detail="caregiver not found")
    lang = caregiver.get("language") or "en"
    all_skills = await db.skills.find({"archived": {"$ne": True}}).to_list(length=200)
    cleared = set(caregiver.get("cleared_skills") or [])
    SIGNABLE = ("ready_to_sign", "needs_practice")
    attempts = await db.attempts.find(
        {"caregiver_id": caregiver_id, "status": {"$in": list(SIGNABLE)}},
    ).to_list(length=500)
    attempted = {
        a["skill_id"]
        for a in attempts
        if a.get("skill_id") and not a.get("reviewed")
    }
    conv = await db.conversations.find_one({"caregiver_id": caregiver_id})
    conv_state = (conv or {}).get("state")
    conv_skill = (conv or {}).get("skill_id")

    def _localized_title(skill: dict) -> str:
        if lang in ("es", "tl"):
            t = (skill.get("translations") or {}).get(lang) or {}
            if t.get("title"):
                return t["title"]
        return skill.get("title") or ""

    def _status_for(skill_id: str) -> str:
        if skill_id in cleared:
            return "cleared"
        if skill_id in attempted:
            return "awaiting_signoff"
        if conv_skill == skill_id:
            if conv_state == "awaiting_video":
                return "practice_video_next"
            if conv_state in ("in_lesson", "quiz"):
                return "in_progress"
        return "todo"

    def _row(skill: dict) -> dict:
        sid = skill["_id"]
        return {
            "id": sid,
            "title": _localized_title(skill),
            "title_en": skill.get("title") or "",
            "step_count": len(skill.get("steps", [])),
            "status": _status_for(sid),
            # Legacy field kept for pre-Stage-2 clients that still check it.
            "has_pending_attempt": sid in attempted,
        }

    cleared_rows = [_row(s) for s in all_skills if s["_id"] in cleared]
    remaining_rows = [_row(s) for s in all_skills if s["_id"] not in cleared]
    return {
        "caregiver": {
            "id": caregiver["_id"],
            "name": caregiver.get("name"),
            "language": lang,
        },
        "cleared": cleared_rows,
        "remaining": remaining_rows,
    }


# Mount sub-routers (chunked upload, jobs, skill-level ops).
# These expose the paths documented in the module docstring above.
router.include_router(_uploads_router)
router.include_router(_jobs_router)
router.include_router(_skills_router)


@router.on_event("startup")
async def _on_startup() -> None:
    """Lazy-sweep any jobs left mid-stage by a prior process."""
    try:
        swept = await sweep_stale_jobs()
        if swept:
            logger.info("lessons: swept %d stale job(s) at startup", swept)
    except Exception as exc:  # noqa: BLE001
        logger.exception("lessons: startup sweep failed: %s", exc)
