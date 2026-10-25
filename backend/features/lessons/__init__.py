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
    db = get_db()
    caregiver = await db.caregivers.find_one({"_id": caregiver_id})
    if not caregiver:
        raise HTTPException(status_code=404, detail="caregiver not found")
    all_skills = await db.skills.find({"archived": {"$ne": True}}).to_list(length=200)
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
