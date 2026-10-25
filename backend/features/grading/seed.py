"""Idempotent in-feature seed for the Glove removal skill.

The Phase-2 seed script (`backend/seed/seed.py`) owns the global
`skills` collection and will remove this skill on a full re-seed. This
module re-ensures the skill at feature import time (and lazily on first
clip upload, as a belt-and-suspenders).

The skill `_id` is a UUID4 hex string, matching the convention set by
the Phase-2 seed. Checks and translations are inlined.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from db import get_db

logger = logging.getLogger("firstshift.grading.seed")

GLOVE_SKILL_TITLE = "Glove removal"

# Developer placeholder translations — flagged in CONTRACTS §10 for a
# pro-translator pass.
_SKILL_ES_TITLE = "Retiro de guantes"
_SKILL_TL_TITLE = "Pagtanggal ng guwantes"

_CHECKS: list[dict] = [
    {"id": "g1", "description": "Gloved fingers pinch the OUTSIDE of the first glove at the wrist", "safety_critical": True},
    {"id": "g2", "description": "Peel the first glove off, turning it inside out",                  "safety_critical": False},
    {"id": "g3", "description": "Hold the removed glove in the still-gloved hand",                  "safety_critical": False},
    {"id": "g4", "description": "Slide bare fingers UNDER the cuff of the second glove, touching only its inside", "safety_critical": True},
    {"id": "g5", "description": "Peel the second glove off over the first, inside out",             "safety_critical": False},
    {"id": "g6", "description": "Discard both gloves in the trash",                                 "safety_critical": False},
    {"id": "g7", "description": "Perform hand hygiene",                                             "safety_critical": False},
]

# Spanish / Tagalog translations for every check description.
_CHECKS_ES: dict[str, str] = {
    "g1": "Pellizca con los dedos enguantados el EXTERIOR del primer guante en la muñeca",
    "g2": "Retira el primer guante, volteándolo al revés",
    "g3": "Sostén el guante retirado en la mano aún enguantada",
    "g4": "Desliza los dedos descubiertos POR DEBAJO del puño del segundo guante, tocando solo su interior",
    "g5": "Retira el segundo guante sobre el primero, al revés",
    "g6": "Desecha ambos guantes en la basura",
    "g7": "Realiza higiene de manos",
}
_CHECKS_TL: dict[str, str] = {
    "g1": "Pinching ng mga daliring may guwantes sa LABAS ng unang guwantes sa pulso",
    "g2": "Hubarin ang unang guwantes, binabaligtad ito",
    "g3": "Hawakan ang hinubarang guwantes sa kamay na may guwantes pa",
    "g4": "Idulas ang hubad na daliri SA ILALIM ng cuff ng pangalawang guwantes, galawin lamang ang loob",
    "g5": "Hubarin ang pangalawang guwantes sa ibabaw ng una, baligtad",
    "g6": "Itapon ang parehong guwantes sa basurahan",
    "g7": "Maghugas ng kamay",
}


def _build_steps(check_lang_map: dict[str, str] | None = None) -> list[dict]:
    """Steps mirror checks n=1..7. start/end/frame_id intentionally null."""
    steps: list[dict] = []
    for i, chk in enumerate(_CHECKS, start=1):
        desc = (check_lang_map or {}).get(chk["id"], chk["description"])
        steps.append({
            "n": i,
            "title": desc,
            "instruction": desc,
            "start": None,
            "end": None,
            "frame_id": None,
        })
    return steps


def _skill_doc() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "_id": uuid.uuid4().hex,
        "title": GLOVE_SKILL_TITLE,
        "steps": _build_steps(),
        "checks": [dict(c) for c in _CHECKS],
        "quiz": [],
        "translations": {
            "es": {"title": _SKILL_ES_TITLE, "steps": [
                {"n": i, "title": _CHECKS_ES[c["id"]], "instruction": _CHECKS_ES[c["id"]]}
                for i, c in enumerate(_CHECKS, start=1)
            ]},
            "tl": {"title": _SKILL_TL_TITLE, "steps": [
                {"n": i, "title": _CHECKS_TL[c["id"]], "instruction": _CHECKS_TL[c["id"]]}
                for i, c in enumerate(_CHECKS, start=1)
            ]},
        },
        "created_at": now,
        "source": "grading-feature-seed",
    }


async def ensure_glove_removal_skill() -> str:
    """Return the `_id` of the Glove removal skill, inserting if absent.

    Guard-by-stable-source: the title alone is NOT a reliable existence
    check — a Care Manager may rename the skill via the lessons editor,
    at which point a re-import of this module would see no "Glove
    removal" row and happily insert a second seed copy. We first probe
    by `source: "grading-feature-seed"` which no editor path ever
    touches, then fall back to the original title probe for forks that
    were seeded before this field existed.
    """
    db = get_db()
    existing = await db.skills.find_one(
        {"source": "grading-feature-seed"}, {"_id": 1}
    )
    if existing:
        return existing["_id"]
    existing = await db.skills.find_one(
        {"title": GLOVE_SKILL_TITLE}, {"_id": 1}
    )
    if existing:
        # Legacy rows without the source tag — backfill the marker so
        # the next call takes the fast path.
        await db.skills.update_one(
            {"_id": existing["_id"]},
            {"$set": {"source": "grading-feature-seed"}},
        )
        return existing["_id"]
    doc = _skill_doc()
    try:
        await db.skills.insert_one(doc)
        logger.info("grading seed: inserted Glove removal skill id=%s", doc["_id"])
    except Exception as exc:  # noqa: BLE001
        # Race condition — another worker just inserted. Re-read.
        logger.warning("grading seed: insert failed (%s); re-reading", exc)
        again = await db.skills.find_one({"title": GLOVE_SKILL_TITLE}, {"_id": 1})
        if again:
            return again["_id"]
        raise
    return doc["_id"]


def schedule_startup_seed() -> None:
    """Fire-and-forget seed task; safe to call at module import time."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.info("grading seed: no running loop at import; relying on lazy ensure")
        return
    loop.create_task(_run_safe())


async def _run_safe() -> None:
    try:
        await ensure_glove_removal_skill()
    except Exception:  # noqa: BLE001
        logger.exception("grading seed: ensure_glove_removal_skill failed")
