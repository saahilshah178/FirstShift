"""plans — seed + backfill helpers.

Called on backend startup by `server.py`. Idempotent.

- `seed_cert_skill_map` — ensures the small cert → skill-ids map exists.
  Resolves by current skill TITLE (CNA covers all 4; HHA covers all
  except Blood pressure). Re-runs on every startup to track renames.
- `backfill_plans` — every existing caregiver gets a `plans` row with
  all active skills in `mode: "learn"` if they don't have one yet.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from db import get_db

logger = logging.getLogger("firstshift.plans.seed")

CERT_SKILL_RULES = {
    "CNA": {
        "Hand hygiene",
        "Glove removal",
        "Blood pressure measurement",
        "Transfer from bed to wheelchair",
    },
    "HHA": {
        "Hand hygiene",
        "Glove removal",
        "Transfer from bed to wheelchair",
    },
}


async def seed_cert_skill_map() -> dict:
    """Resolve cert names → current skill ids and upsert the map."""
    db = get_db()
    skills = await db.skills.find({"archived": {"$ne": True}}, {"_id": 1, "title": 1}).to_list(length=200)
    by_title = {s["title"]: s["_id"] for s in skills}
    summary = {"upserted": 0, "unresolved": []}
    for cert, titles in CERT_SKILL_RULES.items():
        resolved = [by_title[t] for t in titles if t in by_title]
        missing = [t for t in titles if t not in by_title]
        if missing:
            logger.warning("cert_skill_map: %s missing skills: %s", cert, missing)
            summary["unresolved"].extend([{"cert": cert, "title": m} for m in missing])
        await db.cert_skill_map.update_one(
            {"certificate": cert},
            {"$set": {"verify_skill_ids": resolved, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        summary["upserted"] += 1
    return summary


async def backfill_plans() -> dict:
    """For every caregiver missing a `plans` row, create a learn-mode plan."""
    db = get_db()
    skill_ids = [
        s["_id"]
        for s in await db.skills.find({"archived": {"$ne": True}}, {"_id": 1}).to_list(length=200)
    ]
    caregivers = await db.caregivers.find({}, {"_id": 1}).to_list(length=2000)
    now = datetime.now(timezone.utc).isoformat()
    created = 0
    for c in caregivers:
        existing = await db.plans.find_one({"caregiver_id": c["_id"]}, {"_id": 1})
        if existing:
            continue
        try:
            await db.plans.insert_one({
                "_id": uuid.uuid4().hex,
                "caregiver_id": c["_id"],
                "items": [{"skill_id": sid, "mode": "learn"} for sid in skill_ids],
                "created_at": now,
                "updated_at": now,
            })
            created += 1
        except Exception as exc:  # race / duplicate — fine
            logger.warning("backfill_plans: insert race for %s: %s", c["_id"], exc)
    return {"caregivers": len(caregivers), "plans_created": created}


async def startup() -> None:
    """One-shot entrypoint invoked from `server.py@on_startup`."""
    try:
        cert_summary = await seed_cert_skill_map()
        plan_summary = await backfill_plans()
        logger.info(
            "plans startup: cert_map=%s plans=%s", cert_summary, plan_summary,
        )
    except Exception:  # noqa: BLE001
        logger.exception("plans startup failed")
