"""Seed script — see package docstring."""
from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow `python -m backend.seed.seed` (cwd = /app) *and* direct execution
# from inside /app/backend. We make both parents importable.
_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]  # /app/backend
_REPO = _HERE.parents[2]  # /app
for p in (_BACKEND, _REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from media.store import MediaStore  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorGridFSBucket  # noqa: E402
from util.access_code import retry_on_duplicate  # noqa: E402

logger = logging.getLogger("firstshift.seed")

# Collections this script owns (wiped & re-seeded on every run).
_OWNED = ["agencies", "caregivers", "clients", "skills", "attempts", "signoffs"]


# ---------- helpers ----------
_PALETTE = [
    (242, 196, 143),  # warm sand
    (203, 158, 110),  # amber
    (198, 90, 59),  # terracotta
    (120, 150, 118),  # sage
    (90, 120, 130),  # dusty teal
]


def _frame_png(skill_title: str, step_n: int, color: tuple[int, int, int]) -> bytes:
    img = Image.new("RGB", (320, 200), color=color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (320, 36)], fill=(255, 255, 255))
    draw.text((10, 10), f"{skill_title}", fill=(60, 60, 60))
    draw.text((10, 90), f"Step {step_n}", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _tiny_clip() -> tuple[bytes, str]:
    """Return (bytes, content_type) for a placeholder clip stored in GridFS.

    We don't actually have a video encoder available — a tiny WAV passes
    our allowlist and is small enough for a seed stand-in.
    """
    # 0.2s of silence at 8 kHz mono, 8-bit → ~1.6 KB WAV.
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(8000)
        w.writeframes(b"\x80" * 1600)
    return buf.getvalue(), "audio/wav"


def _oid() -> str:
    """Stable string id for seed documents (uuid4 hex)."""
    return uuid.uuid4().hex


# ---------- content ----------
# NOTE: `translations.es` and `translations.tl` strings are PLACEHOLDER
# translations committed by a developer. A professional translator must
# review before this ships to real caregivers.


def _skills_template() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {
            "_id": _oid(),
            "title": "Transfer from bed to wheelchair",
            "steps": [
                {
                    "n": 1,
                    "title": "Lock the wheelchair",
                    "instruction": "Position wheelchair at a 45° angle; engage both brakes.",
                    "start": 0.0,
                    "end": 4.0,
                    "frame_id": None,
                },
                {
                    "n": 2,
                    "title": "Apply gait belt",
                    "instruction": "Place the gait belt around the client's waist; check two-finger slack.",
                    "start": 4.0,
                    "end": 11.0,
                    "frame_id": None,
                },
                {
                    "n": 3,
                    "title": "Pivot and seat",
                    "instruction": "Count '1-2-3', pivot together, lower them gently into the chair.",
                    "start": 11.0,
                    "end": 22.0,
                    "frame_id": None,
                },
                {
                    "n": 4,
                    "title": "Confirm comfort",
                    "instruction": "Ask client if they feel steady; adjust footrests.",
                    "start": 22.0,
                    "end": 28.0,
                    "frame_id": None,
                },
            ],
            "checks": [
                {"id": "c1", "description": "Wheelchair brakes locked", "safety_critical": True},
                {"id": "c2", "description": "Gait belt applied with correct tension", "safety_critical": True},
                {"id": "c3", "description": "Counted down before pivot", "safety_critical": False},
                {"id": "c4", "description": "Footrests adjusted after seating", "safety_critical": False},
                {"id": "c5", "description": "Verbal check-in with client at the end", "safety_critical": False},
            ],
            "quiz": [
                {
                    "id": "q1",
                    "prompt": "What is the correct wheelchair angle for a safe transfer?",
                    "choices": ["Parallel to the bed", "45° to the bed", "Facing the bed"],
                    "answer_index": 1,
                },
                {
                    "id": "q2",
                    "prompt": "Who leads the count before the pivot?",
                    "choices": ["The caregiver", "The client", "Whichever is faster"],
                    "answer_index": 0,
                },
            ],
            "translations": {
                "es": {
                    "title": "Traslado de la cama a la silla de ruedas",
                    "steps": [
                        {"n": 1, "title": "Frena la silla de ruedas", "instruction": "Coloca la silla a 45°; activa ambos frenos."},
                        {"n": 2, "title": "Pon el cinturón de marcha", "instruction": "Coloca el cinturón en la cintura; deja dos dedos de holgura."},
                        {"n": 3, "title": "Pivote y asiento", "instruction": "Cuenta '1-2-3', pivota y bájalo con cuidado."},
                        {"n": 4, "title": "Confirma comodidad", "instruction": "Pregunta si se siente firme; ajusta los reposapiés."},
                    ],
                },
                "tl": {
                    "title": "Paglipat mula higaan papuntang wheelchair",
                    "steps": [
                        {"n": 1, "title": "I-lock ang wheelchair", "instruction": "Ilagay ang wheelchair sa 45°; i-engage ang parehong brake."},
                        {"n": 2, "title": "Ilagay ang gait belt", "instruction": "Ilagay sa baywang; subukan ng dalawang daliri."},
                        {"n": 3, "title": "Pivot at paupo", "instruction": "Magbilang ng '1-2-3', mag-pivot at dahan-dahang paupuin."},
                        {"n": 4, "title": "Kumpirmahin ang ginhawa", "instruction": "Tanungin kung komportable; ayusin ang footrests."},
                    ],
                },
            },
            "created_at": now.isoformat(),
        },
        {
            "_id": _oid(),
            "title": "Hand hygiene",
            "steps": [
                {"n": 1, "title": "Wet hands", "instruction": "Wet hands with clean, running water.", "start": 0.0, "end": 4.0, "frame_id": None},
                {"n": 2, "title": "Apply soap", "instruction": "Apply enough soap to cover all surfaces.", "start": 4.0, "end": 9.0, "frame_id": None},
                {"n": 3, "title": "Scrub 20s", "instruction": "Rub palms, backs, between fingers, under nails for 20 seconds.", "start": 9.0, "end": 29.0, "frame_id": None},
                {"n": 4, "title": "Rinse and dry", "instruction": "Rinse thoroughly; dry with a clean towel.", "start": 29.0, "end": 38.0, "frame_id": None},
            ],
            "checks": [
                {"id": "c1", "description": "Hands fully wet before soap", "safety_critical": False},
                {"id": "c2", "description": "Scrubbed for at least 20 seconds", "safety_critical": True},
                {"id": "c3", "description": "Covered between fingers and under nails", "safety_critical": True},
                {"id": "c4", "description": "Dried with a clean/disposable towel", "safety_critical": False},
            ],
            "quiz": [
                {"id": "q1", "prompt": "Minimum scrub time?", "choices": ["5s", "10s", "20s", "60s"], "answer_index": 2},
                {"id": "q2", "prompt": "Which surface is most often missed?", "choices": ["Palms", "Backs of hands", "Between fingers"], "answer_index": 2},
            ],
            "translations": {
                "es": {
                    "title": "Higiene de manos",
                    "steps": [
                        {"n": 1, "title": "Moja las manos", "instruction": "Moja las manos con agua limpia y corriente."},
                        {"n": 2, "title": "Aplica jabón", "instruction": "Aplica suficiente jabón para cubrir todas las superficies."},
                        {"n": 3, "title": "Frota 20 segundos", "instruction": "Frota palmas, dorsos, entre dedos y uñas durante 20 segundos."},
                        {"n": 4, "title": "Enjuaga y seca", "instruction": "Enjuaga bien; seca con una toalla limpia."},
                    ],
                },
                "tl": {
                    "title": "Paglilinis ng kamay",
                    "steps": [
                        {"n": 1, "title": "Basain ang kamay", "instruction": "Basain ng malinis na tubig na umaagos."},
                        {"n": 2, "title": "Lagyan ng sabon", "instruction": "Lagyan ng sapat na sabon upang matakpan ang lahat."},
                        {"n": 3, "title": "Kuskusin 20 segundo", "instruction": "Kuskusin ang palad, likod, pagitan ng daliri, kuko sa loob ng 20 segundo."},
                        {"n": 4, "title": "Banlawan at patuyuin", "instruction": "Banlawan nang mabuti; patuyuin gamit ang malinis na tuwalya."},
                    ],
                },
            },
            "created_at": now.isoformat(),
        },
        {
            "_id": _oid(),
            "title": "Blood pressure measurement",
            "steps": [
                {"n": 1, "title": "Position arm", "instruction": "Seat client; rest arm at heart level, feet flat.", "start": 0.0, "end": 6.0, "frame_id": None},
                {"n": 2, "title": "Place cuff", "instruction": "Place cuff 2–3 cm above elbow crease; snug but not tight.", "start": 6.0, "end": 15.0, "frame_id": None},
                {"n": 3, "title": "Inflate and read", "instruction": "Inflate to 180 mmHg; slowly deflate while listening/watching.", "start": 15.0, "end": 35.0, "frame_id": None},
                {"n": 4, "title": "Record and inform", "instruction": "Record systolic/diastolic; share result with the client.", "start": 35.0, "end": 45.0, "frame_id": None},
            ],
            "checks": [
                {"id": "c1", "description": "Client seated and still for ≥1 minute before reading", "safety_critical": False},
                {"id": "c2", "description": "Cuff size matches arm circumference", "safety_critical": True},
                {"id": "c3", "description": "Arm at heart level", "safety_critical": True},
                {"id": "c4", "description": "Result read aloud to client", "safety_critical": False},
                {"id": "c5", "description": "Reading documented in chart", "safety_critical": False},
            ],
            "quiz": [
                {"id": "q1", "prompt": "Where should the cuff sit?", "choices": ["Over the elbow", "2–3 cm above elbow crease", "Over the wrist"], "answer_index": 1},
                {"id": "q2", "prompt": "Why rest at heart level?", "choices": ["Comfort", "Accurate reading", "Faster inflation"], "answer_index": 1},
                {"id": "q3", "prompt": "Normal adult reading sits around?", "choices": ["90/60", "120/80", "160/100"], "answer_index": 1},
            ],
            "translations": {
                "es": {
                    "title": "Medición de la presión arterial",
                    "steps": [
                        {"n": 1, "title": "Coloca el brazo", "instruction": "Sienta al cliente; brazo a la altura del corazón, pies planos."},
                        {"n": 2, "title": "Coloca el brazalete", "instruction": "Brazalete 2–3 cm arriba del codo; ajustado sin apretar."},
                        {"n": 3, "title": "Infla y lee", "instruction": "Infla a 180 mmHg; desinfla lentamente mientras lees."},
                        {"n": 4, "title": "Registra e informa", "instruction": "Registra sistólica/diastólica; comparte el resultado."},
                    ],
                },
                "tl": {
                    "title": "Pagsukat ng presyon ng dugo",
                    "steps": [
                        {"n": 1, "title": "Ilagay ang braso", "instruction": "Paupuin ang kliyente; braso sa taas ng puso, patag ang paa."},
                        {"n": 2, "title": "Ilagay ang cuff", "instruction": "Cuff 2–3 cm sa itaas ng siko; sakto, hindi masikip."},
                        {"n": 3, "title": "Pumbo at basahin", "instruction": "Pumbo hanggang 180 mmHg; dahan-dahang bitawan habang nagbabasa."},
                        {"n": 4, "title": "Itala at ipaalam", "instruction": "Itala ang systolic/diastolic; ipaalam sa kliyente."},
                    ],
                },
            },
            "created_at": now.isoformat(),
        },
    ]


# ---------- main ----------
async def seed() -> dict:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "firstshift")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="media")
    store = MediaStore(bucket)

    # Make sure the access_code unique index exists before we insert.
    await db.caregivers.create_index("access_code", unique=True, sparse=True)

    # 1. Wipe owned collections.
    for name in _OWNED:
        await db[name].delete_many({})

    now = datetime.now(timezone.utc)

    # 2. Agencies.
    agencies = [
        {"_id": _oid(), "name": "Sunrise Home Care", "created_at": now.isoformat()},
        {"_id": _oid(), "name": "Harbor Caregivers", "created_at": now.isoformat()},
    ]
    await db.agencies.insert_many(list(agencies))

    # 3. Skills + reference frame uploads.
    skills = _skills_template()
    for s_idx, skill in enumerate(skills):
        for st_idx, step in enumerate(skill["steps"]):
            color = _PALETTE[(s_idx * 2 + st_idx) % len(_PALETTE)]
            png = _frame_png(skill["title"], step["n"], color)
            frame_uuid = await store.save(
                png, "image/png", filename=f"{skill['title']}-step-{step['n']}.png"
            )
            step["frame_id"] = frame_uuid
    await db.skills.insert_many(list(skills))
    skill_ids = [s["_id"] for s in skills]

    # 4. Caregivers (with access codes).
    languages_cycle = ["en", "es", "tl", "en", "es"]
    names = [
        "Alex Johnson",       # en
        "María García",       # es
        "Jovelyn Santos",     # tl
        "Darius Williams",    # en
        "Lucia Hernández",    # es
    ]
    notes = [
        "Two years in dementia care; comfortable with transfers.",
        "Night shifts for 6 months; prefers hygiene / meal prep tasks.",
        "New grad CNA; shadowed for 3 weeks before solo.",
        "Returning aide after 1-year break; refreshing skills.",
        "Bilingual aide; strong with vitals and medication reminders.",
    ]
    caregivers: list[dict] = []
    for i, name in enumerate(names):
        agency = agencies[i % 2]
        hired_at = now - timedelta(days=(i * 5 + 2))
        cleared = skill_ids[: (i % 3)]  # 0, 1, or 2 cleared skills

        async def _insert(code: str, _i=i, _name=name, _agency=agency, _hired=hired_at, _cleared=cleared):
            doc = {
                "_id": _oid(),
                "agency_id": _agency["_id"],
                "name": _name,
                "language": languages_cycle[_i],
                "hired_at": _hired.isoformat(),
                "experience_note": notes[_i],
                "cleared_skills": list(_cleared),
                "access_code": code,
                "created_at": now.isoformat(),
            }
            await db.caregivers.insert_one(doc)
            return doc

        doc = await retry_on_duplicate(_insert)
        caregivers.append(doc)

    # 5. Clients.
    clients = [
        {
            "_id": _oid(),
            "agency_id": agencies[0]["_id"],
            "name": "Mrs. Eleanor Pike",
            "required_skills": [skill_ids[0], skill_ids[1]],
        },
        {
            "_id": _oid(),
            "agency_id": agencies[0]["_id"],
            "name": "Mr. Henry Oshiro",
            "required_skills": [skill_ids[1]],
        },
        {
            "_id": _oid(),
            "agency_id": agencies[1]["_id"],
            "name": "Ms. Priya Natarajan",
            "required_skills": [skill_ids[0], skill_ids[1], skill_ids[2]],
        },
        {
            "_id": _oid(),
            "agency_id": agencies[1]["_id"],
            "name": "Mr. Walter Brooks",
            "required_skills": [skill_ids[2]],
        },
    ]
    await db.clients.insert_many(list(clients))

    # 6. Attempts (upload a tiny placeholder clip per attempt).
    attempts_plan = [
        {"caregiver": 0, "skill": 0, "overall": 82, "pattern": ["pass", "pass", "pass", "unclear", "pass"]},
        {"caregiver": 0, "skill": 1, "overall": 95, "pattern": ["pass", "pass", "pass", "pass"]},
        {"caregiver": 1, "skill": 1, "overall": 70, "pattern": ["pass", "fail", "pass", "unclear"]},
        {"caregiver": 2, "skill": 0, "overall": 55, "pattern": ["fail", "pass", "pass", "pass", "unclear"]},
        {"caregiver": 3, "skill": 2, "overall": 88, "pattern": ["pass", "pass", "pass", "pass", "pass"]},
        {"caregiver": 4, "skill": 2, "overall": 76, "pattern": ["pass", "unclear", "pass", "pass", "pass"]},
    ]
    clip_bytes, clip_mime = _tiny_clip()
    attempts: list[dict] = []
    for i, plan in enumerate(attempts_plan):
        caregiver = caregivers[plan["caregiver"]]
        skill = skills[plan["skill"]]
        clip_uuid = await store.save(
            clip_bytes, clip_mime, filename=f"attempt-{i}.wav"
        )
        checks = []
        for ci, chk in enumerate(skill["checks"]):
            result = plan["pattern"][ci] if ci < len(plan["pattern"]) else "pass"
            checks.append({
                "id": chk["id"],
                "result": result,
                "time": round(2.5 + ci * 3.1, 1),
                "seen": result != "unclear",
            })
        attempts.append({
            "_id": _oid(),
            "caregiver_id": caregiver["_id"],
            "skill_id": skill["_id"],
            "clip_id": clip_uuid,
            "checks": checks,
            "overall": plan["overall"],
            "created_at": (now - timedelta(days=(len(attempts_plan) - i))).isoformat(),
        })
    await db.attempts.insert_many(list(attempts))

    # 7. Signoffs on first three attempts.
    signoff_specs = [
        {"idx": 0, "signer": "Rachel Kim, RN", "decision": "approved",     "note": "Clean transfer. Ready for solo."},
        {"idx": 1, "signer": "Rachel Kim, RN", "decision": "approved",     "note": "Textbook hygiene."},
        {"idx": 2, "signer": "Daniel Osei",    "decision": "needs_rework", "note": "Scrub time under 20s on second attempt."},
    ]
    signoffs = []
    for spec in signoff_specs:
        attempt = attempts[spec["idx"]]
        signoffs.append({
            "_id": _oid(),
            "attempt_id": attempt["_id"],
            "caregiver_id": attempt["caregiver_id"],
            "skill_id": attempt["skill_id"],
            "signer": spec["signer"],
            "decision": spec["decision"],
            "note": spec["note"],
            "at": now.isoformat(),
        })
    await db.signoffs.insert_many(list(signoffs))

    summary = {
        "agencies": len(agencies),
        "caregivers": len(caregivers),
        "clients": len(clients),
        "skills": len(skills),
        "attempts": len(attempts),
        "signoffs": len(signoffs),
        "caregiver_access_codes": [
            {"name": c["name"], "code": c["access_code"]} for c in caregivers
        ],
    }
    client.close()
    return summary


async def seed_if_empty() -> dict | None:
    """Run `seed()` only when the agencies collection is empty."""
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "firstshift")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    count = await db.agencies.estimated_document_count()
    client.close()
    if count > 0:
        logger.info("seed: agencies already present (%d); skipping", count)
        return None
    logger.info("seed: agencies empty — seeding now")
    summary = await seed()
    logger.info("seed: inserted %s", {k: v for k, v in summary.items() if k != "caregiver_access_codes"})
    for item in summary["caregiver_access_codes"]:
        logger.info("seed: caregiver '%s' -> code %s", item["name"], item["code"])
    return summary


def _print_summary(summary: dict) -> None:
    for k in ("agencies", "caregivers", "clients", "skills", "attempts", "signoffs"):
        print(f"  {k:12s} {summary[k]}")
    print("  caregiver access codes:")
    for item in summary["caregiver_access_codes"]:
        print(f"    {item['code']}  {item['name']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = asyncio.run(seed())
    print("seed complete:")
    _print_summary(summary)
