"""Dedupe skills: hard-delete loser rows and migrate all references
(attempts, signoffs, caregivers.cleared_skills, clients.required_skills,
lesson_jobs.skill_id) to the winner id.

Rule used to pick the winner (per `docs/merge/mvp-hardening.md`):
newest version with the most content (frames, quiz, full translations).

Dedup map is hard-coded here so re-runs on an already-deduped DB are
inert (the loser rows don't exist anymore — the script logs 'already
deduped' and exits 0).

Usage::

    python -m scripts.dedupe_skills          # from /app/backend
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path


# Winner → list of loser skill ids.
DEDUP_MAP: dict[str, list[str]] = {
    # Transfer / wheelchair family — winner is the lessons/record v3 publish
    # with full translations + real reference video + frames.
    "c7691d94cef347f6bc03f3fc808939bd": [
        "f071e83edefe4d5aaecb68dc22dc35b1",  # seed Transfer (step-level translations only)
        "6184365a18544eb1a50294cc247a44d6",  # Transfer From Bed to Chair With a Gait Belt (less content)
    ],
    # Glove family — keep the seed title; fix #6 upgrades it with frames,
    # quiz, and full check translations.
    "c60f1d3a9c44493b8c5e2fd5d3644d82": [
        "6285be18f3e44afba30b649ce77ca8c0",  # Removing Gloves Technique
    ],
}


def _load_env() -> None:
    env_path = Path("/app/backend/.env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


async def main() -> int:
    _load_env()
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("dedupe")

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "firstshift")]

    total_deleted = 0
    total_migrated_attempts = 0
    total_migrated_signoffs = 0
    total_migrated_cleared = 0
    total_migrated_clients = 0
    total_migrated_jobs = 0

    for winner_id, loser_ids in DEDUP_MAP.items():
        winner = await db.skills.find_one({"_id": winner_id}, {"_id": 1, "title": 1})
        if not winner:
            log.error("winner %s not found — aborting dedup for this family", winner_id)
            continue
        log.info("winner: %s  '%s'", winner_id, winner.get("title"))

        for loser_id in loser_ids:
            loser = await db.skills.find_one({"_id": loser_id}, {"_id": 1, "title": 1})
            if not loser:
                log.info("  loser %s: already removed (idempotent)", loser_id)
                continue
            log.info("  loser %s: '%s' — migrating refs then deleting", loser_id, loser.get("title"))

            # 1. attempts.skill_id → winner
            r = await db.attempts.update_many({"skill_id": loser_id}, {"$set": {"skill_id": winner_id}})
            total_migrated_attempts += r.modified_count
            log.info("    attempts migrated: %d", r.modified_count)

            # 2. signoffs.skill_id → winner
            r = await db.signoffs.update_many({"skill_id": loser_id}, {"$set": {"skill_id": winner_id}})
            total_migrated_signoffs += r.modified_count
            log.info("    signoffs migrated: %d", r.modified_count)

            # 3. caregivers.cleared_skills: swap loser id → winner id (addToSet then pull keeps the array deduped)
            r_add = await db.caregivers.update_many(
                {"cleared_skills": loser_id},
                {"$addToSet": {"cleared_skills": winner_id}},
            )
            r_pull = await db.caregivers.update_many(
                {"cleared_skills": loser_id},
                {"$pull": {"cleared_skills": loser_id}},
            )
            total_migrated_cleared += r_pull.modified_count
            log.info(
                "    caregivers cleared_skills: added-winner=%d  pulled-loser=%d",
                r_add.modified_count, r_pull.modified_count,
            )

            # 4. clients.required_skills: same pattern
            r_add = await db.clients.update_many(
                {"required_skills": loser_id},
                {"$addToSet": {"required_skills": winner_id}},
            )
            r_pull = await db.clients.update_many(
                {"required_skills": loser_id},
                {"$pull": {"required_skills": loser_id}},
            )
            total_migrated_clients += r_pull.modified_count
            log.info(
                "    clients required_skills: added-winner=%d  pulled-loser=%d",
                r_add.modified_count, r_pull.modified_count,
            )

            # 5. lesson_jobs.skill_id → winner (drafts linked to the loser now point at the winner)
            r = await db.lesson_jobs.update_many(
                {"skill_id": loser_id},
                {"$set": {"skill_id": winner_id}},
            )
            total_migrated_jobs += r.modified_count
            log.info("    lesson_jobs migrated: %d", r.modified_count)

            # 6. hard-delete the skill row.
            d = await db.skills.delete_one({"_id": loser_id})
            total_deleted += d.deleted_count
            log.info("    skills row deleted: %d", d.deleted_count)

    log.info(
        "done: deleted=%d  attempts=%d  signoffs=%d  cleared=%d  clients=%d  jobs=%d",
        total_deleted,
        total_migrated_attempts,
        total_migrated_signoffs,
        total_migrated_cleared,
        total_migrated_clients,
        total_migrated_jobs,
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
