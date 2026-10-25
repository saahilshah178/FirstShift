"""Clamp attempt check timestamps to clip duration.

Shared helper used by:
- `backend/seed/seed.py` — seeded attempts whose synthetic timestamps
  are generated BEFORE the final clip length is known (the clip is a
  10 s placeholder today; the real Chippewa cut will be 12 s). Checks
  past the clip end would cause the sign-off reviewer to jump past the
  end of playback.
- `backend/scripts/reseed_jovelyn_from_source.py` — when the real
  source clip lands, re-clamp so timestamps fit the new length.

Policy:
- If `clip_duration` is a positive number, every check's `time`
  (seconds) is clamped to `min(time, clip_duration - margin)`.
- `margin` defaults to 0.2 s so the UI can still show a frame around
  the pinned timestamp without landing on the exact last frame.
- `None` / missing timestamps are left as-is.
"""
from __future__ import annotations

from typing import Iterable


def clamp_check_times(
    checks: Iterable[dict],
    *,
    clip_duration: float | None,
    margin: float = 0.2,
) -> list[dict]:
    """Return a NEW list of check dicts with `time` clamped to the clip.

    Caller is responsible for persisting the result; this helper is pure.
    """
    out: list[dict] = []
    if clip_duration is None or clip_duration <= 0:
        return [dict(c) for c in checks]
    cap = max(0.0, float(clip_duration) - float(margin))
    for c in checks:
        new = dict(c)
        t = new.get("time")
        if isinstance(t, (int, float)):
            new["time"] = round(min(float(t), cap), 2)
        out.append(new)
    return out


__all__ = ["clamp_check_times"]
