"""In-process job runner for the lessons feature.

- Each job runs under `asyncio.create_task`.
- A background heartbeat loop writes `heartbeat_at` every 5 s while a
  stage is executing.
- `sweep_stale_jobs()` flips any non-terminal job whose heartbeat is
  >30 s old to `failed` with error "Interrupted (server restart)".
  It runs once at startup AND lazily on every `GET /jobs(/{id})`.
- Retries resume from the first missing output: existing `video_id`
  skips `converting`; existing draft with steps + frames skips those.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from db import get_db

from .pipeline import (
    stage_analyze,
    stage_convert,
    stage_extract_frames,
    utcnow_iso,
)

logger = logging.getLogger("firstshift.lessons.runner")

TERMINAL_STATES = {"ready", "published", "failed"}
HEARTBEAT_INTERVAL_S = 5.0
HEARTBEAT_STALE_S = 30.0

# active tasks keyed by job_id so we don't double-run.
_active: dict[str, asyncio.Task] = {}


async def _heartbeat(job_id: str) -> None:
    db = get_db()
    while True:
        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            await db.lesson_jobs.update_one(
                {"_id": job_id},
                {"$set": {"heartbeat_at": utcnow_iso()}},
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("heartbeat update failed for %s: %s", job_id, exc)


async def _set_status(job_id: str, status: str, *, extra: dict[str, Any] | None = None) -> None:
    db = get_db()
    payload: dict[str, Any] = {
        "status": status,
        "updated_at": utcnow_iso(),
        "heartbeat_at": utcnow_iso(),
    }
    if extra:
        payload.update(extra)
    await db.lesson_jobs.update_one({"_id": job_id}, {"$set": payload, "$inc": {"draft_rev": 1}})


async def _run_pipeline(job_id: str, assembled_path: str | None) -> None:
    """Full pipeline, picking up at the first stage with missing output."""
    db = get_db()
    job = await db.lesson_jobs.find_one({"_id": job_id})
    if not job:
        logger.warning("runner: job %s vanished", job_id)
        return

    hb_task = asyncio.create_task(_heartbeat(job_id))
    try:
        # Stage: convert (skipped if video_id already exists).
        if not job.get("video_id"):
            if not assembled_path or not os.path.exists(assembled_path):
                raise RuntimeError("Converter needs the assembled upload, but it is missing on disk.")
            await _set_status(job_id, "converting")
            video_id, duration_s, _size = await stage_convert(assembled_path)
            await db.lesson_jobs.update_one(
                {"_id": job_id},
                {"$set": {
                    "video_id": video_id,
                    "duration_s": duration_s,
                    "updated_at": utcnow_iso(),
                    "heartbeat_at": utcnow_iso(),
                },
                 "$inc": {"draft_rev": 1}},
            )
            # Clean up the assembled file.
            try:
                os.remove(assembled_path)
            except Exception:  # noqa: BLE001
                pass
            job = await db.lesson_jobs.find_one({"_id": job_id})
        else:
            # Retry path — nothing to do here, duration_s already stored.
            pass

        duration_s = float(job.get("duration_s") or 0.0)
        video_id = job["video_id"]

        # Stage: analyze (skipped if draft has steps).
        draft = job.get("draft") or {}
        if not (draft.get("steps") or draft.get("checks")):
            await _set_status(job_id, "analyzing")
            draft, problems = await stage_analyze(video_id, duration_s)
            await db.lesson_jobs.update_one(
                {"_id": job_id},
                {"$set": {
                    "draft": draft,
                    "problems": problems,
                    "updated_at": utcnow_iso(),
                    "heartbeat_at": utcnow_iso(),
                }, "$inc": {"draft_rev": 1}},
            )
            job = await db.lesson_jobs.find_one({"_id": job_id})
            draft = job["draft"]

        # Stage: extract frames (skipped if every step already has a frame_id).
        steps = draft.get("steps") or []
        needs_frames = any(not s.get("frame_id") for s in steps)
        if needs_frames and steps:
            await _set_status(job_id, "extracting_frames")
            new_draft = await stage_extract_frames(video_id, draft)
            await db.lesson_jobs.update_one(
                {"_id": job_id},
                {"$set": {
                    "draft": new_draft,
                    "updated_at": utcnow_iso(),
                    "heartbeat_at": utcnow_iso(),
                }, "$inc": {"draft_rev": 1}},
            )

        await _set_status(job_id, "ready", extra={"error": ""})
    except Exception as exc:  # noqa: BLE001
        logger.exception("job %s failed: %s", job_id, exc)
        msg = str(exc).strip() or exc.__class__.__name__
        # Keep it a one-line human message.
        msg = msg.splitlines()[0][:300]
        await _set_status(job_id, "failed", extra={"error": msg})
    finally:
        hb_task.cancel()
        try:
            await hb_task
        except Exception:  # noqa: BLE001
            pass
        _active.pop(job_id, None)


def kick_job(job_id: str, assembled_path: str | None = None) -> None:
    """Fire-and-forget pipeline run. Idempotent per job_id."""
    if job_id in _active and not _active[job_id].done():
        logger.info("kick_job: %s already running; ignoring", job_id)
        return
    loop = asyncio.get_event_loop()
    task = loop.create_task(_run_pipeline(job_id, assembled_path))
    _active[job_id] = task


async def sweep_stale_jobs() -> int:
    """Flip jobs with stale heartbeat to failed. Returns number swept."""
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_STALE_S)).isoformat()
    result = await db.lesson_jobs.update_many(
        {
            "status": {"$nin": list(TERMINAL_STATES)},
            "heartbeat_at": {"$lt": cutoff},
            "_id": {"$nin": [jid for jid, t in _active.items() if not t.done()]},
        },
        {
            "$set": {
                "status": "failed",
                "error": "Interrupted (server restart)",
                "updated_at": utcnow_iso(),
            },
            "$inc": {"draft_rev": 1},
        },
    )
    return int(result.modified_count or 0)
