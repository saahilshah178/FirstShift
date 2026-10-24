"""Questions service stub.

Returns a realistic answer payload. In Phase 2+ this will call Gemini
with the caregiver's question + lesson/skill context.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def answer_question(caregiver_id: str, text: str) -> dict:
    """Answer a free-form caregiver question.

    Returns:
        {
          "question_id": str,
          "caregiver_id": str,
          "question": str,
          "answer": str,
          "citations": [
            {"skill_id": str, "step_n": int, "snippet": str}
          ],
          "confidence": float (0..1),
          "answered_at": ISO-8601 str,
          "model": str,
        }
    """
    return {
        "question_id": uuid.uuid4().hex,
        "caregiver_id": caregiver_id,
        "question": text,
        "answer": (
            "Wash hands for at least 20 seconds using warm water and soap, "
            "covering palms, backs, between fingers, and under nails."
        ),
        "citations": [
            {
                "skill_id": "skill_hand_hygiene",
                "step_n": 3,
                "snippet": "Rub hands palm-to-palm for 20 seconds.",
            }
        ],
        "confidence": 0.82,
        "answered_at": datetime.now(timezone.utc).isoformat(),
        "model": "stub",
    }
