"""Repair `caregivers.cleared_skills` ↔ `signoffs` inconsistencies.

Rule (chosen in Batch-2 planning): a skill ONLY counts as cleared when
an approving signoff doc exists for that (caregiver_id, skill_id). Any
`cleared_skills` entry that lacks an approving signoff is an orphan
and is stripped.

Also: for every (caregiver_id, skill_id) pair we strip, if there is a
legacy attempt row without a `status` field, infer a signable status
from its checks/overall so the queue surfaces it. This recovers the
"hero sign-off moment" for Jovelyn's Transfer attempt and any similar
legacy row.

Idempotent — re-running after a successful pass finds nothing to do.

Run with:
    python -m backend.scripts.repair_cleared_skills

The script accepts both `approve` and legacy seed value `approved`
when deciding whether a signoff is approving.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Allow `python -m backend.scripts.repair_cleared_skills` from /app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient


APPROVE_VALUES = {"approve", "approved"}


def _infer_status(attempt: dict) -> tuple[str, str]:
    """Return (status, verdict) for a legacy attempt without status.

    Matches `features/grading/background.py` mapping:
      verdict `pass`  -> status `ready_to_sign`
      verdict `retry` -> status `needs_practice`
    """
    checks = attempt.get("checks") or []
    has_fail = any(c.get("result") == "fail" for c in checks)
    overall = attempt.get("overall")
    if has_fail or (isinstance(overall, (int, float)) and overall < 70):
        return "needs_practice", "retry"
    return "ready_to_sign", "pass"


async def main() -> int:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "firstshift")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    skills = await db.skills.find({}, {"title": 1}).to_list(length=200)
    title_by_id = {s["_id"]: s.get("title", "(unknown)") for s in skills}

    caregivers = await db.caregivers.find({}).to_list(length=500)
    strips: list[tuple[str, str, str, str]] = []  # (cg_id, cg_name, skill_id, skill_title)
    for cg in caregivers:
        cleared = list(cg.get("cleared_skills") or [])
        if not cleared:
            continue
        signoffs = await db.signoffs.find({"caregiver_id": cg["_id"]}).to_list(length=200)
        approved_skills = {
            s.get("skill_id") for s in signoffs if s.get("decision") in APPROVE_VALUES
        }
        for sid in cleared:
            if sid in approved_skills:
                continue
            strips.append((cg["_id"], cg.get("name", "?"), sid, title_by_id.get(sid, "(unknown)")))

    if not strips:
        print("[repair_cleared_skills] nothing to strip; cleared_skills ↔ signoffs are consistent.")
    else:
        print(f"[repair_cleared_skills] stripping {len(strips)} orphan clear(s):")
        for cg_id, cg_name, sid, sskill in strips:
            print(f"  - {cg_name!r} ({cg_id[:8]}) → skill {sskill!r} ({sid[:8]}): no approving signoff")
            await db.caregivers.update_one(
                {"_id": cg_id},
                {"$pull": {"cleared_skills": sid}},
            )

    # Backfill: resurrect queue visibility for any legacy attempt we just
    # exposed by stripping. Only touches rows with no `status` set.
    backfills: list[tuple[str, str, str, str]] = []  # (att_id, cg_name, sskill, status)
    for cg_id, cg_name, sid, sskill in strips:
        attempts = await db.attempts.find({
            "caregiver_id": cg_id,
            "skill_id": sid,
            "status": {"$in": [None]},
        }).to_list(length=50)
        for att in attempts:
            status, verdict = _infer_status(att)
            await db.attempts.update_one(
                {"_id": att["_id"]},
                {"$set": {"status": status, "verdict": verdict}},
            )
            backfills.append((att["_id"], cg_name, sskill, status))

    if backfills:
        print(f"[repair_cleared_skills] backfilled status on {len(backfills)} legacy attempt(s):")
        for att_id, cg_name, sskill, status in backfills:
            print(f"  - attempt {att_id[:8]} ({cg_name!r} / {sskill!r}) → status={status}")
    else:
        print("[repair_cleared_skills] no legacy attempts needed status backfill.")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
