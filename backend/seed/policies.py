"""Seed 3 agency policies (idempotent).

Developer-written placeholders. Flagged in docs/CHANGELOG.md; user
will revise copy. Called once from `features/channel/__init__.py` at
startup so forks can test the question-loop without manual seeding.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from db import get_db

logger = logging.getLogger("firstshift.seed.policies")

POLICIES: list[dict] = [
    {
        "title": "Client refuses care",
        "text": (
            "If a client refuses any part of care, stop immediately and respect the "
            "refusal. Ask once, calmly, what they would prefer. Do not argue, scold, "
            "or try again more than once. Document the refusal in the shift notes, "
            "including the time, what was refused, what the client said, and any "
            "behaviours you observed.\n\n"
            "Notify the care manager by the end of the shift. If the refusal involves "
            "medication, a scheduled transfer, or anything flagged safety-critical in "
            "the care plan, call the care manager immediately — don't wait."
        ),
    },
    {
        "title": "Client falls",
        "text": (
            "If a client falls, do not try to lift them alone. Stay with the client, "
            "check for responsiveness, visible injury, bleeding, pain, or confusion. "
            "If they are unresponsive, bleeding heavily, cannot move a limb, or complain "
            "of head/neck/back pain, call 911 immediately and keep them still.\n\n"
            "If the client is alert and uninjured, help them to a sitting position only "
            "when they feel steady, and only if you can do so without lifting. Notify the "
            "care manager within 15 minutes and complete an incident report before the end "
            "of the shift, including time, location, witnessed vs. found, and the client's "
            "own account."
        ),
    },
    {
        "title": "Running late to a shift",
        "text": (
            "If you expect to be more than 10 minutes late, call or text the care manager "
            "as soon as you know — not when you arrive. Give the realistic arrival time, "
            "not the one you wish were true. The care manager will decide whether to tell "
            "the client, cover the gap, or reschedule.\n\n"
            "Running late more than twice in a 30-day window triggers a conversation about "
            "scheduling. Repeated no-shows or no-notice lateness are grounds for removal "
            "from the schedule."
        ),
    },
]


async def seed_policies() -> int:
    """Insert any missing policies by title; returns number inserted."""
    db = get_db()
    inserted = 0
    for p in POLICIES:
        existing = await db.policies.find_one({"title": p["title"]}, {"_id": 1})
        if existing:
            continue
        await db.policies.insert_one({
            "_id": uuid.uuid4().hex,
            "title": p["title"],
            "text": p["text"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        inserted += 1
    if inserted:
        logger.info("seeded %d policy row(s)", inserted)
    return inserted
