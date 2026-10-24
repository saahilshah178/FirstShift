"""Background grading task: runs `grade_clip`, writes the attempt back.

Keeps the HTTP upload request from blocking on Gemini. A single
in-process asyncio task per attempt; failures are captured on the
attempt document rather than lost.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from db import get_db
from features.grading.pipeline import GradingError
from services.grading_service import grade_clip

logger = logging.getLogger("firstshift.grading.background")


_VERDICT_TO_STATUS = {
    "retake": "retake_required",
    "retry": "needs_practice",
    "pass": "ready_to_sign",
}


async def _run(attempt_id: str, skill_id: str, caregiver_id: str, clip_id: str) -> None:
    db = get_db()
    try:
        result = await grade_clip(skill_id, caregiver_id, clip_id)
    except GradingError as exc:
        logger.exception("grading failed (GradingError): %s", exc)
        await _finalise_error(db, attempt_id, str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("grading failed (unexpected): %s", exc)
        await _finalise_error(db, attempt_id, f"unexpected: {exc!s}")
        return

    verdict = result.get("verdict") or "retry"
    status = _VERDICT_TO_STATUS.get(verdict, "grading_error")
    update = {
        "$set": {
            "checks": result.get("checks", []),
            "overall": result.get("overall"),
            "verdict": verdict,
            "score": result.get("score"),
            "message_for_caregiver": result.get("message_for_caregiver", ""),
            "runs_used": result.get("runs_used", 0),
            "graded_once": result.get("graded_once", False),
            "raw_runs": result.get("raw_runs", []),
            "frame_ids": result.get("frame_ids", []),
            "status": status,
            "error": None,
            "model": result.get("model"),
            "graded_at": datetime.now(timezone.utc).isoformat(),
        }
    }
    await db.attempts.update_one({"_id": attempt_id}, update)
    logger.info("attempt %s graded -> status=%s verdict=%s", attempt_id, status, verdict)


async def _finalise_error(db, attempt_id: str, error: str) -> None:
    await db.attempts.update_one(
        {"_id": attempt_id},
        {"$set": {
            "status": "grading_error",
            "error": error,
            "graded_at": datetime.now(timezone.utc).isoformat(),
        }},
    )


def enqueue_grade(
    attempt_id: str, skill_id: str, caregiver_id: str, clip_id: str,
) -> None:
    """Fire-and-forget grading of an attempt in the current event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.error("no running loop for enqueue_grade(%s)", attempt_id)
        return
    loop.create_task(_run(attempt_id, skill_id, caregiver_id, clip_id))


# ---- stale sweeper (10 min) ----
STALE_MINUTES = 10


async def mark_stale_grading() -> int:
    """Flip any `status == grading` older than 10 min to `grading_error`."""
    from datetime import timedelta
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES)).isoformat()
    res = await db.attempts.update_many(
        {"status": "grading", "created_at": {"$lt": cutoff}},
        {"$set": {"status": "grading_error", "error": "grading timed out"}},
    )
    return res.modified_count
