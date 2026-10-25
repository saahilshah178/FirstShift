"""Hard-delete orphan `lesson_jobs` rows.

Context — Fix #13 (lazy edit + delete-on-publish):

- `POST /api/lessons/skills/{id}/edit` is now LAZY — it returns a
  deterministic `job_id = "edit-{skill_id}"` and does NOT insert a
  `lesson_jobs` row until the first `PUT /jobs/{job_id}/draft`.
- `POST /api/lessons/jobs/{job_id}/publish` deletes any OTHER draft
  rows pointing at the same `skill_id` on success.

This script cleans up stale rows that pre-date the lazy flow (or that
would otherwise accumulate) using these rules:

  Delete a `lesson_jobs` row iff:
    - status in {"ready", "failed"}
    - updated_at older than N minutes (default 60)
    - AND one of:
        (a) `skill_id` is unset  (abandoned "new skill" draft), or
        (b) `skill_id` points to a published skill AND `_id` is not
            the canonical `"edit-{skill_id}"` row (legacy duplicate), or
        (c) `skill_id` is set but no such skill exists (victim of a
            prior dedup pass).

Idempotent — second run with the same clock finds nothing new.

Run with:
    python -m backend.scripts.cleanup_orphan_drafts [--older-than 60]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient


DELETABLE_STATUSES = {"ready", "failed"}
DEFAULT_OLDER_THAN_MINUTES = 60


def _parse_iso(s: str | None) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


async def main(older_than_min: int) -> int:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "firstshift")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_min)
    print(f"[cleanup_orphan_drafts] cutoff: anything updated_at < {cutoff.isoformat()}")

    jobs = await db.lesson_jobs.find({"status": {"$in": list(DELETABLE_STATUSES)}}).to_list(length=1000)
    published_skill_ids = {
        s["_id"]
        for s in await db.skills.find({}, {"_id": 1}).to_list(length=500)
    }

    kept: list[dict] = []
    deleted: list[dict] = []
    for j in jobs:
        updated_at = _parse_iso(j.get("updated_at"))
        if not updated_at or updated_at > cutoff:
            kept.append(j)
            continue
        skill_id = j.get("skill_id")
        canonical_edit_id = f"edit-{skill_id}" if skill_id else None
        reason: str | None = None
        if not skill_id:
            reason = "no skill_id (abandoned new-skill draft)"
        elif skill_id not in published_skill_ids:
            reason = f"skill {skill_id[:8]} no longer exists"
        elif j["_id"] != canonical_edit_id:
            reason = f"duplicate edit draft (canonical is {canonical_edit_id})"
        if reason is None:
            kept.append(j)
            continue
        deleted.append({"id": j["_id"], "skill_id": skill_id, "status": j.get("status"), "reason": reason})
        await db.lesson_jobs.delete_one({"_id": j["_id"]})

    if not deleted:
        print("[cleanup_orphan_drafts] nothing to delete.")
    else:
        print(f"[cleanup_orphan_drafts] deleted {len(deleted)} orphan draft(s):")
        for d in deleted:
            sid = (d["skill_id"] or "")[:8] or "—"
            print(f"  - job {d['id'][:8]} status={d['status']} skill={sid} :: {d['reason']}")

    client.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--older-than", type=int, default=DEFAULT_OLDER_THAN_MINUTES,
                    help=f"minutes (default {DEFAULT_OLDER_THAN_MINUTES})")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.older_than)))
