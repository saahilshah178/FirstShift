"""Upgrade the 'Glove removal' skill with:
- 7 reference frame PNGs (one per step) via MediaStore.
- Short unique step titles (not duplicating the instruction).
- Longer unique instructions (one sentence each).
- A 2-question quiz.
- Spanish + Tagalog translations for the 7 checks (same ids) and the quiz.
- Linked into the first client's required_skills if not already present.

Idempotent: skips frame upload if `frame_id` already set; replaces the
quiz / check translations wholesale (so a re-run just overwrites them
with the latest content from this script).

Usage::

    python -m scripts.upgrade_glove_removal           # from /app/backend
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
from pathlib import Path


GLOVE_SKILL_ID = "c60f1d3a9c44493b8c5e2fd5d3644d82"


_PALETTE = [
    (247, 213, 150),  # warm cream
    (221, 180, 127),
    (203, 148, 100),
    (174, 130, 100),
    (152, 108, 80),
    (120, 90, 70),
    (90, 70, 55),
]


# Short, unique step titles + distinct longer instructions.
_STEP_UPGRADES = [
    {"n": 1, "title": "Pinch outside",
     "instruction": "Pinch the OUTSIDE of the first glove at the wrist with your other gloved hand."},
    {"n": 2, "title": "Peel first glove",
     "instruction": "Peel the glove down and off, turning it inside-out as you pull."},
    {"n": 3, "title": "Bundle in gloved hand",
     "instruction": "Keep the removed glove bundled in the fingers of the still-gloved hand."},
    {"n": 4, "title": "Slide under cuff",
     "instruction": "Slide bare fingers UNDER the cuff of the second glove — touch only the inside."},
    {"n": 5, "title": "Peel over the first",
     "instruction": "Peel the second glove down over the first, trapping both inside-out."},
    {"n": 6, "title": "Discard",
     "instruction": "Drop both gloves straight into the trash — no mid-air handling."},
    {"n": 7, "title": "Wash hands",
     "instruction": "Wash hands with soap for 20 seconds or use alcohol-based rub."},
]

_QUIZ = [
    {
        "id": "q1",
        "prompt": "When you grab the first glove, which part of the glove do you touch?",
        "choices": ["The inside cuff", "The outside at the wrist", "The fingertips"],
        "answer_index": 1,
    },
    {
        "id": "q2",
        "prompt": "What's the last step after both gloves are off?",
        "choices": [
            "Rinse the gloves and reuse",
            "Document in the chart",
            "Wash hands or use alcohol rub",
        ],
        "answer_index": 2,
    },
]

_CHECK_TRANSLATIONS_ES = [
    {"id": "g1", "description": "Pellizca el EXTERIOR del primer guante en la muñeca"},
    {"id": "g2", "description": "Retira el primer guante, dejándolo del revés"},
    {"id": "g3", "description": "Sostiene el guante retirado en la mano aún enguantada"},
    {"id": "g4", "description": "Desliza los dedos bajo el puño del segundo guante — toca solo el interior"},
    {"id": "g5", "description": "Retira el segundo guante sobre el primero, del revés"},
    {"id": "g6", "description": "Descarta ambos guantes en la basura"},
    {"id": "g7", "description": "Realiza higiene de manos"},
]

_CHECK_TRANSLATIONS_TL = [
    {"id": "g1", "description": "Kurutin ang LABAS ng unang gwantes sa pulso"},
    {"id": "g2", "description": "Hubarin ang unang gwantes, bina-baligtad habang hinihila"},
    {"id": "g3", "description": "Hawakan ang tanggal na gwantes sa kabilang gwantesang kamay"},
    {"id": "g4", "description": "Isingit ang mga nakadalgang daliri sa ILALIM ng kuwelyo — hipuin lang ang loob"},
    {"id": "g5", "description": "Hubarin ang pangalawang gwantes sa ibabaw ng una, baligtad"},
    {"id": "g6", "description": "Itapon ang dalawang gwantes sa basura"},
    {"id": "g7", "description": "Maghugas ng kamay"},
]

_QUIZ_TRANSLATIONS_ES = [
    {
        "id": "q1",
        "prompt": "Cuando agarras el primer guante, ¿qué parte del guante tocas?",
        "choices": ["El puño interior", "La parte exterior en la muñeca", "Las puntas de los dedos"],
    },
    {
        "id": "q2",
        "prompt": "¿Cuál es el último paso después de retirar ambos guantes?",
        "choices": [
            "Enjuagar los guantes y reutilizarlos",
            "Documentar en el historial",
            "Lavarse las manos o usar alcohol en gel",
        ],
    },
]

_QUIZ_TRANSLATIONS_TL = [
    {
        "id": "q1",
        "prompt": "Kapag hinawakan mo ang unang gwantes, aling bahagi ng gwantes ang hinihipo mo?",
        "choices": ["Loob ng kuwelyo", "Labas sa may pulso", "Mga dulo ng daliri"],
    },
    {
        "id": "q2",
        "prompt": "Ano ang huling hakbang pagkatapos tanggalin ang dalawang gwantes?",
        "choices": [
            "Banlawan at gamitin muli",
            "Itala sa chart",
            "Maghugas ng kamay o gumamit ng alcohol rub",
        ],
    },
]

_STEP_TRANSLATIONS_ES = [
    {"n": 1, "title": "Pellizca el exterior", "instruction": "Pellizca el EXTERIOR del primer guante en la muñeca con la otra mano enguantada."},
    {"n": 2, "title": "Retira el primer guante", "instruction": "Baja el guante y retíralo del revés mientras tiras."},
    {"n": 3, "title": "Enrolla en la mano enguantada", "instruction": "Mantén el guante retirado en los dedos de la mano aún enguantada."},
    {"n": 4, "title": "Desliza bajo el puño", "instruction": "Desliza los dedos BAJO el puño del segundo guante — toca solo el interior."},
    {"n": 5, "title": "Retira sobre el primero", "instruction": "Retira el segundo guante sobre el primero, quedando ambos del revés."},
    {"n": 6, "title": "Descarta", "instruction": "Tira ambos guantes directo a la basura — sin manipular en el aire."},
    {"n": 7, "title": "Lávate las manos", "instruction": "Lávate las manos con jabón por 20 segundos o usa alcohol en gel."},
]

_STEP_TRANSLATIONS_TL = [
    {"n": 1, "title": "Kurutin ang labas", "instruction": "Kurutin ang LABAS ng unang gwantes sa pulso gamit ang kabilang nakadalgang kamay."},
    {"n": 2, "title": "Hubarin ang unang gwantes", "instruction": "Ibaba ang gwantes at hubarin, binabaligtad habang hinihila."},
    {"n": 3, "title": "Hawakan sa kabila", "instruction": "Panatilihin ang tanggal na gwantes sa mga daliri ng kabilang gwantesang kamay."},
    {"n": 4, "title": "Isingit sa ilalim", "instruction": "Isingit ang mga nakadalgang daliri sa ILALIM ng pangalawang gwantes — hipuin lang ang loob."},
    {"n": 5, "title": "Hubarin sa ibabaw", "instruction": "Hubarin ang pangalawang gwantes sa ibabaw ng una, parehong baligtad."},
    {"n": 6, "title": "Itapon", "instruction": "Itapon pareho ng gwantes sa basura — walang paghihipuan sa hangin."},
    {"n": 7, "title": "Maghugas ng kamay", "instruction": "Maghugas ng kamay gamit ang sabon ng 20 segundo o alcohol rub."},
]


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


def _frame_png(n: int, color: tuple[int, int, int]) -> bytes:
    """Produce a labelled 480x270 PNG. Lightweight stand-in reference frame."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (480, 270), color)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        subfont = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
        subfont = ImageFont.load_default()
    draw.text((24, 18), "Glove removal", fill=(255, 255, 255), font=subfont)
    draw.text((24, 60), f"Step {n}", fill=(255, 255, 255), font=font)
    draw.text((24, 110), _STEP_UPGRADES[n - 1]["title"], fill=(255, 255, 255), font=subfont)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def main() -> int:
    _load_env()
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket  # noqa: E402

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("glove-upgrade")

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "firstshift")]
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="media")

    skill = await db.skills.find_one({"_id": GLOVE_SKILL_ID})
    if not skill:
        log.error("Glove removal skill %s not found", GLOVE_SKILL_ID)
        return 1

    # 1. Upload a frame per step if missing.
    new_steps: list[dict] = []
    for st in skill.get("steps") or []:
        n = int(st.get("n") or 0)
        upgrade = next((x for x in _STEP_UPGRADES if x["n"] == n), None)
        new_step = {
            "n": n,
            "title": upgrade["title"] if upgrade else st.get("title") or f"Step {n}",
            "instruction": upgrade["instruction"] if upgrade else st.get("instruction") or "",
            "start": st.get("start"),
            "end": st.get("end"),
            "frame_id": st.get("frame_id"),
        }
        if not new_step["frame_id"]:
            png = _frame_png(n, _PALETTE[(n - 1) % len(_PALETTE)])
            import uuid as _uuid
            uid = _uuid.uuid4().hex
            await bucket.upload_from_stream(
                f"glove-step-{n}.png",
                png,
                metadata={"uuid": uid, "content_type": "image/png"},
            )
            new_step["frame_id"] = uid
            log.info("uploaded frame for step %d → %s", n, uid)
        new_steps.append(new_step)

    # 2. Write quiz if missing.
    quiz = list(skill.get("quiz") or [])
    if not quiz:
        quiz = _QUIZ

    # 3. Translations: merge in new checks + quiz; keep existing step titles if present
    #    (the lessons/record translator may have improved them already).
    translations = dict(skill.get("translations") or {})
    es = dict(translations.get("es") or {})
    es["title"] = es.get("title") or "Retiro de guantes"
    es["steps"] = es.get("steps") or _STEP_TRANSLATIONS_ES
    es["checks"] = _CHECK_TRANSLATIONS_ES
    es["quiz"] = _QUIZ_TRANSLATIONS_ES
    es["status"] = es.get("status") or "machine"
    translations["es"] = es

    tl = dict(translations.get("tl") or {})
    tl["title"] = tl.get("title") or "Pagtanggal ng gwantes"
    tl["steps"] = tl.get("steps") or _STEP_TRANSLATIONS_TL
    tl["checks"] = _CHECK_TRANSLATIONS_TL
    tl["quiz"] = _QUIZ_TRANSLATIONS_TL
    tl["status"] = tl.get("status") or "machine"
    translations["tl"] = tl

    await db.skills.update_one(
        {"_id": GLOVE_SKILL_ID},
        {"$set": {
            "steps": new_steps,
            "quiz": quiz,
            "translations": translations,
            "version": int(skill.get("version") or 1),
        }},
    )
    log.info("skill upgraded: steps=%d quiz=%d checks=%d",
             len(new_steps), len(quiz), len(skill.get("checks") or []))

    # 4. Link into the first client that doesn't already require it.
    client_row = await db.clients.find_one({"required_skills": {"$ne": GLOVE_SKILL_ID}}, sort=[("name", 1)])
    if client_row:
        await db.clients.update_one(
            {"_id": client_row["_id"]},
            {"$addToSet": {"required_skills": GLOVE_SKILL_ID}},
        )
        log.info("linked Glove removal into client '%s'", client_row.get("name"))
    else:
        log.info("every client already requires Glove removal")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
