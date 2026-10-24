"""Lessons service stub.

Returns a realistic lesson/skill payload. In Phase 2+ this will call
Gemini on a reference video to auto-extract steps, checks and a quiz.
"""
from __future__ import annotations


def build_lesson(video_id: str) -> dict:
    """Build a lesson payload from a reference video.

    Returns:
        {
          "video_id": str,
          "title": str,
          "steps": [
            {"n": int, "title": str, "instruction": str,
             "start": float, "end": float, "frame_id": str|None}
          ],
          "checks": [
            {"id": str, "description": str, "safety_critical": bool}
          ],
          "quiz": [
            {"id": str, "prompt": str,
             "choices": [str, ...], "answer_index": int}
          ],
          "translations": {"es": {...}, "tl": {...}},
          "model": str,
        }
    """
    return {
        "video_id": video_id,
        "title": "Hand hygiene before resident contact",
        "steps": [
            {
                "n": 1,
                "title": "Wet hands",
                "instruction": "Wet hands with clean running water.",
                "start": 0.0,
                "end": 4.0,
                "frame_id": None,
            },
            {
                "n": 2,
                "title": "Apply soap",
                "instruction": "Apply enough soap to cover all surfaces.",
                "start": 4.0,
                "end": 9.0,
                "frame_id": None,
            },
            {
                "n": 3,
                "title": "Scrub 20s",
                "instruction": "Rub hands palm-to-palm for 20 seconds.",
                "start": 9.0,
                "end": 29.0,
                "frame_id": None,
            },
        ],
        "checks": [
            {"id": "c1", "description": "Hands wet before soap", "safety_critical": False},
            {"id": "c2", "description": "Scrubbed at least 20s", "safety_critical": True},
            {"id": "c3", "description": "Dried with clean towel", "safety_critical": False},
        ],
        "quiz": [
            {
                "id": "q1",
                "prompt": "Minimum scrub time?",
                "choices": ["5s", "10s", "20s", "60s"],
                "answer_index": 2,
            }
        ],
        "translations": {
            "es": {"title": "Higiene de manos antes del contacto"},
            "tl": {"title": "Paglilinis ng kamay bago makipag-ugnayan"},
        },
        "model": "stub",
    }
