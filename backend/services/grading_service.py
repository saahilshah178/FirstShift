"""Grading service stub.

Returns a realistic grading payload. In Phase 2+ this will call Gemini
on the uploaded clip (see `backend/ai/gemini.py`).
"""
from __future__ import annotations

from datetime import datetime, timezone


def grade_clip(skill_id: str, caregiver_id: str, clip_id: str) -> dict:
    """Grade a submitted clip for a skill.

    Returns:
        {
          "skill_id": str,
          "caregiver_id": str,
          "clip_id": str,
          "checks": [
            {"id": str, "description": str, "result": "pass"|"fail"|"unclear",
             "time": float, "seen": bool, "safety_critical": bool}
          ],
          "overall": "pass"|"fail"|"needs_review",
          "score": float (0..1),
          "created_at": ISO-8601 str,
          "model": str (which model did the grading; "stub" in Phase 1),
        }
    """
    return {
        "skill_id": skill_id,
        "caregiver_id": caregiver_id,
        "clip_id": clip_id,
        "checks": [
            {
                "id": "c1",
                "description": "Washed hands before contact",
                "result": "pass",
                "time": 3.2,
                "seen": True,
                "safety_critical": True,
            },
            {
                "id": "c2",
                "description": "Applied gloves correctly",
                "result": "pass",
                "time": 7.4,
                "seen": True,
                "safety_critical": True,
            },
            {
                "id": "c3",
                "description": "Verbally confirmed resident identity",
                "result": "unclear",
                "time": 12.1,
                "seen": False,
                "safety_critical": False,
            },
        ],
        "overall": "needs_review",
        "score": 0.67,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": "stub",
    }
