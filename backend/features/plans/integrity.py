"""Startup integrity sweep (Stage 3 — Item D).

For every caregiver, every skill id in `cleared_skills` MUST have an
approved sign-off with a clip. Any id that does not → remove from
`cleared_skills` and log a warning.

Approved sign-off = `signoffs` doc with `decision: "approve"` + an
attempt row referencing a `clip_id`. Call `run_integrity_sweep()` from
`server.py@on_startup`. Idempotent; log is `firstshift.plans.integrity`.
"""
from __future__ import annotations

import logging

from db import get_db

logger = logging.getLogger("firstshift.plans.integrity")


async def run_integrity_sweep() -> dict:
    db = get_db()
    caregivers = await db.caregivers.find({}, {"_id": 1, "name": 1, "cleared_skills": 1}).to_list(length=2000)
    corrections = 0
    affected: list[dict] = []
    for c in caregivers:
        cleared = list(c.get("cleared_skills") or [])
        if not cleared:
            continue
        # Approved sign-offs for this caregiver mapped by skill_id.
        signoffs = await db.signoffs.find(
            {"caregiver_id": c["_id"], "decision": "approve"},
            {"attempt_id": 1, "skill_id": 1},
        ).to_list(length=200)
        approved_skill_ids = {s["skill_id"] for s in signoffs if s.get("skill_id")}
        # Also require the referenced attempt to have a clip_id so the brief's
        # "approved sign-off WITH a clip" rule is enforced end-to-end.
        attempt_ids = [s["attempt_id"] for s in signoffs if s.get("attempt_id")]
        attempts_with_clips = set()
        if attempt_ids:
            rows = await db.attempts.find(
                {"_id": {"$in": attempt_ids}, "clip_id": {"$exists": True, "$ne": None}},
                {"_id": 1, "skill_id": 1},
            ).to_list(length=500)
            attempts_with_clips = {r["skill_id"] for r in rows if r.get("skill_id")}
        valid = approved_skill_ids & attempts_with_clips

        bad = [sid for sid in cleared if sid not in valid]
        if not bad:
            continue
        await db.caregivers.update_one(
            {"_id": c["_id"]},
            {"$pull": {"cleared_skills": {"$in": bad}}},
        )
        corrections += len(bad)
        affected.append({"caregiver_id": c["_id"], "name": c.get("name"), "removed": bad})
        logger.warning(
            "integrity: caregiver=%s removed %d bogus cleared_skills: %s",
            c.get("name"), len(bad), bad,
        )
    summary = {"caregivers_scanned": len(caregivers), "corrections": corrections, "affected": affected}
    logger.info("integrity sweep: %s", summary)
    return summary
