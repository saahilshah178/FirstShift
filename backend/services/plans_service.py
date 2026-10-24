"""Plans service stub.

Returns a realistic remediation-plan payload. In Phase 2+ this will
call Gemini with the caregiver's history + a free-text note from ops.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def build_plan(caregiver_id: str, note_text: str) -> dict:
    """Build a remediation / learning plan for a caregiver.

    Returns:
        {
          "plan_id": str,
          "caregiver_id": str,
          "note": str,
          "items": [
            {"skill_id": str, "action": "review"|"reattempt"|"shadow",
             "due_in_days": int, "reason": str}
          ],
          "created_at": ISO-8601 str,
          "model": str,
        }
    """
    return {
        "plan_id": uuid.uuid4().hex,
        "caregiver_id": caregiver_id,
        "note": note_text,
        "items": [
            {
                "skill_id": "skill_hand_hygiene",
                "action": "review",
                "due_in_days": 2,
                "reason": "Scrub duration flagged as unclear on last attempt.",
            },
            {
                "skill_id": "skill_transfer_bed_chair",
                "action": "shadow",
                "due_in_days": 7,
                "reason": "Observed missing gait-belt step in prior clip.",
            },
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": "stub",
    }
