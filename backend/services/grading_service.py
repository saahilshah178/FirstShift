"""Grading service — real Gemini-backed implementation.

The `grade_clip` function below replaces the Phase-1 stub. It is
**pure**: it does not touch the `attempts` collection. The caller
(the `grading` feature's background job) persists the attempt.

Contract shape (matches `docs/CONTRACTS.md`) plus additive keys:
`verdict`, `message_for_caregiver`, `runs_used`, `graded_once`,
`raw_runs`, and per-check `note`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from features.grading.pipeline import grade_clip_pipeline


async def grade_clip(
    skill_id: str,
    caregiver_id: str,
    clip_id: str,
) -> dict:
    """Grade a clip. Async; the caller must await.

    Returns the contract dict:
    {
      "skill_id", "caregiver_id", "clip_id",
      "checks": [{"id","description","result":"pass"|"fail"|"unclear",
                  "time": float, "seen": bool, "safety_critical": bool,
                  "note": str}],
      "overall": "pass"|"fail"|"needs_review",
      "score": float (0..1),
      "created_at": ISO-8601, "model": GEMINI_MODEL,
      # additive:
      "verdict": "pass"|"retry"|"retake",
      "message_for_caregiver": str,
      "runs_used": int,
      "graded_once": bool,
      "raw_runs": [ ... ],
    }
    """
    pipeline = await grade_clip_pipeline(skill_id, caregiver_id, clip_id)
    pipeline["created_at"] = datetime.now(timezone.utc).isoformat()
    return pipeline
