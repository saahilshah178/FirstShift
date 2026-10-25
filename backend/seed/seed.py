"""Seed script — Phase-2 base content.

Stage 1 (2026-02-25): see `docs/CHANGELOG.md` for the full list of changes.
Highlights:
- Alex Johnson's `access_code` is DETERMINISTIC `2TBAFX`.
- Alex has `cleared_skills: []` and NO seeded attempt (per Item B — the
  live-upload path through `/c/2TBAFX` is the test instead).
- Jovelyn's seeded attempt is signable: `status: "ready_to_sign"`,
  `reviewed: False`, `graded_at` set, `checks[]` mirror the Transfer
  skill's current checks (same ids, descriptions, safety_critical).
- All stored clips (even seeded ones) go through
  `backend/media/encode.py::encode_mp4` so the output lives in the same
  one-encoder audit trail as live uploads.
- Blood pressure quiz trimmed to 2. Transfer stays at 2 (unchanged).
- Hand hygiene / Blood pressure / Transfer now ship with full es + tl
  `checks` and `quiz` translations (hand-authored placeholders; a
  pro-translator pass is tracked in CONTRACTS §10).
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]  # /app/backend
_REPO = _HERE.parents[2]  # /app
for p in (_BACKEND, _REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND / ".env")

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from media.encode import encode_mp4  # noqa: E402
from media.store import MediaStore  # noqa: E402
from features.grading.clamp import clamp_check_times  # noqa: E402
from util.access_code import retry_on_duplicate  # noqa: E402

logger = logging.getLogger("firstshift.seed")

# Collections this script owns (wiped & re-seeded on every run).
_OWNED = ["agencies", "caregivers", "clients", "skills", "attempts", "signoffs",
          "plans", "incidents", "cert_skill_map", "refresher_drafts"]


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


def _asset_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "assets" / name


async def _encoded_clip_bytes(src: Path, duration_hint: float | None = None) -> bytes:
    """Encode `src` through the single media encoder, return the bytes.

    Every seeded clip ships through the same encoder every live upload
    uses (CONTRACTS §4 / Stage 1 single-encoder audit). The hint lets
    the budget-aware pass pick a bitrate without a second ffprobe.
    """
    with tempfile.TemporaryDirectory(prefix="fs-seed-enc-") as tmp:
        out = Path(tmp) / "out.mp4"
        await encode_mp4(src, out, duration_s=duration_hint)
        return out.read_bytes()


async def _attempt_placeholder_clip_bytes() -> bytes:
    """Return the encoded bytes for the seeded Jovelyn attempt clip.

    Honest placeholder: NOT fabricated caregiver footage. 10 s of SMPTE
    colour bars with an on-video label that reads
    "Jovelyn Santos — seed placeholder (awaiting real transfer footage)".
    Replace via the Care Manager's "Replace source video" button on the
    Transfer skill (writes a fresh video + re-extracts step frames; the
    `backend/scripts/reseed_jovelyn_from_source.py` helper can also
    swap this clip for a cut of the uploaded source video).
    """
    label = (
        "Jovelyn Santos \u2014 seed placeholder\\n"
        "awaiting real transfer footage"
    )
    with tempfile.TemporaryDirectory(prefix="fs-seed-src-") as tmp:
        src = Path(tmp) / "placeholder-source.mp4"
        # SMPTE bars (motion-aware palette), overlay with the label.
        import subprocess
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi",
            "-i", "smptehdbars=size=640x360:rate=24:duration=10",
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=mono:sample_rate=22050",
            "-shortest",
            "-vf",
            (
                "drawbox=y=ih-70:color=black@0.65:width=iw:height=70:t=fill,"
                f"drawtext=text='{label}':fontcolor=white:fontsize=22:"
                "x=(w-text_w)/2:y=h-55"
            ),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k",
            "-movflags", "+faststart",
            str(src),
        ]
        r = subprocess.run(cmd, check=False, capture_output=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(
                f"placeholder generation failed: "
                f"{r.stderr.decode('utf-8', 'replace')[:300]}"
            )
        # Route through the single encoder helper so faststart / audio
        # bitrate / long-side policy match every other stored clip.
        return await _encoded_clip_bytes(src, duration_hint=10.0)


def _oid() -> str:
    return uuid.uuid4().hex


# ---------- content ----------
# NOTE: `translations.es` and `translations.tl` strings are PLACEHOLDER
# translations committed by a developer. A professional translator must
# review before this ships to real caregivers.
# Stage 1 — Hand hygiene / Blood pressure / Transfer now ship with full
# es + tl checks + quiz translations (previously 0 for both).


def _skills_template() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {
            "_id": _oid(),
            "title": "Transfer from bed to wheelchair",
            "steps": [
                {"n": 1, "title": "Lock the wheelchair",
                 "instruction": "Position wheelchair at a 45° angle; engage both brakes.",
                 "start": 0.0, "end": 4.0, "frame_id": None},
                {"n": 2, "title": "Apply gait belt",
                 "instruction": "Place the gait belt around the client's waist; check two-finger slack.",
                 "start": 4.0, "end": 11.0, "frame_id": None},
                {"n": 3, "title": "Pivot and seat",
                 "instruction": "Count '1-2-3', pivot together, lower them gently into the chair.",
                 "start": 11.0, "end": 22.0, "frame_id": None},
                {"n": 4, "title": "Confirm comfort",
                 "instruction": "Ask client if they feel steady; adjust footrests.",
                 "start": 22.0, "end": 28.0, "frame_id": None},
            ],
            "checks": [
                {"id": "c1", "description": "Wheelchair brakes locked", "safety_critical": True},
                {"id": "c2", "description": "Gait belt applied with correct tension", "safety_critical": True},
                {"id": "c3", "description": "Counted down before pivot", "safety_critical": False},
                {"id": "c4", "description": "Footrests adjusted after seating", "safety_critical": False},
                {"id": "c5", "description": "Verbal check-in with client at the end", "safety_critical": False},
            ],
            "quiz": [
                {"id": "q1",
                 "prompt": "What is the correct wheelchair angle for a safe transfer?",
                 "choices": ["Parallel to the bed", "45° to the bed", "Facing the bed"],
                 "answer_index": 1},
                {"id": "q2",
                 "prompt": "Who leads the count before the pivot?",
                 "choices": ["The caregiver", "The client", "Whichever is faster"],
                 "answer_index": 0},
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
                    "checks": [
                        {"id": "c1", "description": "Frenos de la silla puestos"},
                        {"id": "c2", "description": "Cinturón de marcha con la tensión correcta"},
                        {"id": "c3", "description": "Contaste antes de pivotar"},
                        {"id": "c4", "description": "Reposapiés ajustados tras sentar"},
                        {"id": "c5", "description": "Confirmaste con el cliente al final"},
                    ],
                    "quiz": [
                        {"id": "q1",
                         "prompt": "¿Cuál es el ángulo correcto de la silla para un traslado seguro?",
                         "choices": ["Paralela a la cama", "A 45° de la cama", "Frente a la cama"]},
                        {"id": "q2",
                         "prompt": "¿Quién lleva la cuenta antes del pivote?",
                         "choices": ["La cuidadora", "El cliente", "Quien sea más rápido"]},
                    ],
                    "status": "machine",
                },
                "tl": {
                    "title": "Paglipat mula higaan papuntang wheelchair",
                    "steps": [
                        {"n": 1, "title": "I-lock ang wheelchair", "instruction": "Ilagay ang wheelchair sa 45°; i-engage ang parehong brake."},
                        {"n": 2, "title": "Ilagay ang gait belt", "instruction": "Ilagay sa baywang; subukan ng dalawang daliri."},
                        {"n": 3, "title": "Pivot at paupo", "instruction": "Magbilang ng '1-2-3', mag-pivot at dahan-dahang paupuin."},
                        {"n": 4, "title": "Kumpirmahin ang ginhawa", "instruction": "Tanungin kung komportable; ayusin ang footrests."},
                    ],
                    "checks": [
                        {"id": "c1", "description": "Naka-lock ang brake ng wheelchair"},
                        {"id": "c2", "description": "Tamang higpit ang gait belt"},
                        {"id": "c3", "description": "Nagbilang bago mag-pivot"},
                        {"id": "c4", "description": "Naayos ang footrest pagkatapos paupuin"},
                        {"id": "c5", "description": "Nagtanong sa kliyente sa huli"},
                    ],
                    "quiz": [
                        {"id": "q1",
                         "prompt": "Ano ang tamang anggulo ng wheelchair para sa ligtas na paglipat?",
                         "choices": ["Katabi ng higaan", "45° sa higaan", "Nakaharap sa higaan"]},
                        {"id": "q2",
                         "prompt": "Sino ang nagbibilang bago mag-pivot?",
                         "choices": ["Ang caregiver", "Ang kliyente", "Kung sino ang mas mabilis"]},
                    ],
                    "status": "machine",
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
                {"id": "q1", "prompt": "Minimum scrub time?", "choices": ["5s", "10s", "20s"], "answer_index": 2},
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
                    "checks": [
                        {"id": "c1", "description": "Manos completamente mojadas antes del jabón"},
                        {"id": "c2", "description": "Frotado durante al menos 20 segundos"},
                        {"id": "c3", "description": "Cubriste entre los dedos y bajo las uñas"},
                        {"id": "c4", "description": "Secaste con una toalla limpia o desechable"},
                    ],
                    "quiz": [
                        {"id": "q1",
                         "prompt": "¿Tiempo mínimo de frotado?",
                         "choices": ["5s", "10s", "20s"]},
                        {"id": "q2",
                         "prompt": "¿Qué superficie se olvida con más frecuencia?",
                         "choices": ["Las palmas", "El dorso", "Entre los dedos"]},
                    ],
                    "status": "machine",
                },
                "tl": {
                    "title": "Paglilinis ng kamay",
                    "steps": [
                        {"n": 1, "title": "Basain ang kamay", "instruction": "Basain ng malinis na tubig na umaagos."},
                        {"n": 2, "title": "Lagyan ng sabon", "instruction": "Lagyan ng sapat na sabon upang matakpan ang lahat."},
                        {"n": 3, "title": "Kuskusin 20 segundo", "instruction": "Kuskusin ang palad, likod, pagitan ng daliri, kuko sa loob ng 20 segundo."},
                        {"n": 4, "title": "Banlawan at patuyuin", "instruction": "Banlawan nang mabuti; patuyuin gamit ang malinis na tuwalya."},
                    ],
                    "checks": [
                        {"id": "c1", "description": "Lubos na basa ang kamay bago sabunin"},
                        {"id": "c2", "description": "Kuskos ng hindi bababa sa 20 segundo"},
                        {"id": "c3", "description": "Natakpan ang pagitan ng daliri at ilalim ng kuko"},
                        {"id": "c4", "description": "Pinatuyong may malinis o disposable na tuwalya"},
                    ],
                    "quiz": [
                        {"id": "q1",
                         "prompt": "Ano ang pinakamababang oras ng pagkuskos?",
                         "choices": ["5s", "10s", "20s"]},
                        {"id": "q2",
                         "prompt": "Aling bahagi ang madalas makalimutan?",
                         "choices": ["Mga palad", "Likod ng kamay", "Pagitan ng mga daliri"]},
                    ],
                    "status": "machine",
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
            # Stage 1 — trimmed from 3 to 2 (Item F).
            "quiz": [
                {"id": "q1", "prompt": "Where should the cuff sit?",
                 "choices": ["Over the elbow", "2–3 cm above elbow crease", "Over the wrist"],
                 "answer_index": 1},
                {"id": "q2", "prompt": "Why rest the arm at heart level?",
                 "choices": ["Comfort", "Accurate reading", "Faster inflation"],
                 "answer_index": 1},
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
                    "checks": [
                        {"id": "c1", "description": "El cliente estuvo sentado y quieto ≥1 minuto antes de medir"},
                        {"id": "c2", "description": "El tamaño del brazalete coincide con el brazo"},
                        {"id": "c3", "description": "Brazo a la altura del corazón"},
                        {"id": "c4", "description": "Resultado dicho en voz alta al cliente"},
                        {"id": "c5", "description": "Lectura registrada en el historial"},
                    ],
                    "quiz": [
                        {"id": "q1",
                         "prompt": "¿Dónde debe colocarse el brazalete?",
                         "choices": ["Sobre el codo", "2–3 cm arriba del codo", "Sobre la muñeca"]},
                        {"id": "q2",
                         "prompt": "¿Por qué el brazo a la altura del corazón?",
                         "choices": ["Comodidad", "Lectura precisa", "Inflado más rápido"]},
                    ],
                    "status": "machine",
                },
                "tl": {
                    "title": "Pagsukat ng presyon ng dugo",
                    "steps": [
                        {"n": 1, "title": "Ilagay ang braso", "instruction": "Paupuin ang kliyente; braso sa taas ng puso, patag ang paa."},
                        {"n": 2, "title": "Ilagay ang cuff", "instruction": "Cuff 2–3 cm sa itaas ng siko; sakto, hindi masikip."},
                        {"n": 3, "title": "Pumbo at basahin", "instruction": "Pumbo hanggang 180 mmHg; dahan-dahang bitawan habang nagbabasa."},
                        {"n": 4, "title": "Itala at ipaalam", "instruction": "Itala ang systolic/diastolic; ipaalam sa kliyente."},
                    ],
                    "checks": [
                        {"id": "c1", "description": "Nakaupo at tahimik ang kliyente ng ≥1 minuto bago sukatin"},
                        {"id": "c2", "description": "Angkop ang laki ng cuff sa braso"},
                        {"id": "c3", "description": "Braso sa taas ng puso"},
                        {"id": "c4", "description": "Ibinahagi nang malakas ang resulta sa kliyente"},
                        {"id": "c5", "description": "Naitala ang resulta sa chart"},
                    ],
                    "quiz": [
                        {"id": "q1",
                         "prompt": "Saan dapat ilagay ang cuff?",
                         "choices": ["Sa ibabaw ng siko", "2–3 cm sa itaas ng siko", "Sa pulso"]},
                        {"id": "q2",
                         "prompt": "Bakit braso sa taas ng puso?",
                         "choices": ["Komportable", "Tumpak na basa", "Mas mabilis pumbo"]},
                    ],
                    "status": "machine",
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

    # 3. Skills. Stage-1 brief forbids placeholder-image blocks on skills
    #    without a source video — ALL seed skills ship WITHOUT a video, so
    #    every step's `frame_id` stays `None` and the UI renders the honest
    #    "No image yet" state. A Care Manager can upload the real video via
    #    `POST /api/lessons/skills/{id}/replace_source_video` and that path
    #    will populate `frame_id`s from real frames.
    skills = _skills_template()
    for skill in skills:
        skill["video_id"] = None
        for step in skill["steps"]:
            step["frame_id"] = None
    await db.skills.insert_many(list(skills))
    skill_ids = [s["_id"] for s in skills]

    # 4. Caregivers (Alex deterministic; others via retry_on_duplicate).
    languages_cycle = ["en", "es", "tl", "en", "es"]
    names = [
        "Alex Johnson",       # en  — deterministic 2TBAFX; no cleared skills
        "María García",       # es
        "Jovelyn Santos",     # tl  — Transfer attempt ready to sign
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
        if name == "Alex Johnson":
            cleared: list[str] = []
            code = "2TBAFX"
            doc = {
                "_id": _oid(),
                "agency_id": agency["_id"],
                "name": name,
                "language": languages_cycle[i],
                "hired_at": hired_at.isoformat(),
                "experience_note": notes[i],
                "cleared_skills": cleared,
                "access_code": code,
                "created_at": now.isoformat(),
            }
            await db.caregivers.insert_one(doc)
            caregivers.append(doc)
            continue

        cleared = list(skill_ids[: (i % 3)])  # 0, 1, or 2 cleared skills

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

    cg_by_name = {c["name"]: c for c in caregivers}

    # 5. Clients.
    clients = [
        {"_id": _oid(), "agency_id": agencies[0]["_id"],
         "name": "Mrs. Eleanor Pike",
         "required_skills": [skill_ids[0], skill_ids[1]]},
        {"_id": _oid(), "agency_id": agencies[0]["_id"],
         "name": "Mr. Henry Oshiro",
         "required_skills": [skill_ids[1]]},
        {"_id": _oid(), "agency_id": agencies[1]["_id"],
         "name": "Ms. Priya Natarajan",
         "required_skills": [skill_ids[0], skill_ids[1], skill_ids[2]]},
        {"_id": _oid(), "agency_id": agencies[1]["_id"],
         "name": "Mr. Walter Brooks",
         "required_skills": [skill_ids[2]]},
    ]
    await db.clients.insert_many(list(clients))

    # 6. Attempts.
    # Stage 1 (Item B): Alex is REMOVED from this list; the live upload at
    # `/c/2TBAFX` is the proving ground now.
    attempts_plan = [
        # María — Hand hygiene (approved below)
        {"caregiver": "María García", "skill_idx": 1,
         "overall": 95, "pattern": ["pass", "pass", "pass", "pass"],
         "status": "ready_to_sign", "clip_source": "placeholder"},
        # Jovelyn — Transfer — ready to sign (the hero demo clip)
        {"caregiver": "Jovelyn Santos", "skill_idx": 0,
         "overall": 70, "pattern": ["pass", "fail", "pass", "unclear", "pass"],
         "status": "ready_to_sign", "clip_source": "jovelyn-transfer"},
        # Darius — Blood pressure
        {"caregiver": "Darius Williams", "skill_idx": 2,
         "overall": 88, "pattern": ["pass", "pass", "pass", "pass", "pass"],
         "status": "ready_to_sign", "clip_source": "placeholder"},
        # Lucia — Blood pressure
        {"caregiver": "Lucia Hernández", "skill_idx": 2,
         "overall": 76, "pattern": ["pass", "unclear", "pass", "pass", "pass"],
         "status": "ready_to_sign", "clip_source": "placeholder"},
    ]

    # Jovelyn gets the generated 10 s placeholder (routed through the
    # single encoder). Others get a short placeholder (same encoder path).
    jovelyn_clip = await _attempt_placeholder_clip_bytes()
    short_src = _asset_path("placeholder.mp4")
    short_clip = await _encoded_clip_bytes(short_src, duration_hint=2.0) if short_src.exists() else jovelyn_clip

    attempts: list[dict] = []
    for i, plan in enumerate(attempts_plan):
        caregiver = cg_by_name[plan["caregiver"]]
        skill = skills[plan["skill_idx"]]
        if plan["clip_source"] == "jovelyn-transfer":
            clip_bytes = jovelyn_clip
            filename = "attempt-jovelyn-transfer.mp4"
            clip_source = "seed-transfer-placeholder"
        else:
            clip_bytes = short_clip
            filename = f"attempt-{i}.mp4"
            clip_source = "seed-placeholder"
        clip_uuid = await store.save(clip_bytes, "video/mp4", filename=filename)

        # Mirror the skill's current checks on every attempt.
        checks = []
        for ci, chk in enumerate(skill["checks"]):
            result = plan["pattern"][ci] if ci < len(plan["pattern"]) else "pass"
            checks.append({
                "id": chk["id"],
                "description": chk["description"],
                "safety_critical": bool(chk.get("safety_critical", False)),
                "result": result,
                "time": round(2.5 + ci * 3.1, 1),
                "seen": result != "unclear",
                "note": "",
            })
        attempt_duration = 10.0 if plan["clip_source"] == "jovelyn-transfer" else 2.5
        # Clamp any check that would land past the end of this (placeholder)
        # clip so a sign-off reviewer never jumps past playback. The real
        # Chippewa cut will be longer than 10 s and the untouched offsets
        # fit inside it (reseed_jovelyn_from_source re-runs the clamp with
        # the real duration anyway).
        checks = clamp_check_times(checks, clip_duration=attempt_duration)
        created_at = (now - timedelta(days=(len(attempts_plan) - i))).isoformat()
        graded_at = (now - timedelta(days=(len(attempts_plan) - i), hours=-1)).isoformat()
        attempts.append({
            "_id": _oid(),
            "caregiver_id": caregiver["_id"],
            "skill_id": skill["_id"],
            "clip_id": clip_uuid,
            "clip_source": clip_source,
            "duration": attempt_duration,
            "checks": checks,
            "overall": plan["overall"],
            "status": plan["status"],
            "verdict": "pass" if plan["overall"] >= 85 else "retry",
            "score": plan["overall"] / 100.0,
            "message_for_caregiver": "",
            "runs_used": 1,
            "graded_once": True,
            "raw_runs": [],
            "frame_ids": [],
            "error": None,
            "reviewed": False,
            "created_at": created_at,
            "graded_at": graded_at,
        })
    await db.attempts.insert_many(list(attempts))

    # 7. Signoffs — Approve María + Darius (hand hygiene / BP). Jovelyn's
    # Transfer stays unreviewed so it shows up in the Sign-off queue.
    signoff_specs = [
        {"attempt_name": "María García",   "skill_idx": 1, "signer": "Rachel Kim, RN",
         "decision": "approve",   "note": "Textbook hygiene."},
        {"attempt_name": "Darius Williams","skill_idx": 2, "signer": "Rachel Kim, RN",
         "decision": "approve",   "note": "Steady technique."},
    ]
    signoffs = []
    reviewed_attempt_ids: list[str] = []
    for spec in signoff_specs:
        attempt = next(
            (a for a in attempts if a["caregiver_id"] == cg_by_name[spec["attempt_name"]]["_id"]
             and a["skill_id"] == skills[spec["skill_idx"]]["_id"]),
            None,
        )
        if not attempt:
            continue
        reviewed_attempt_ids.append(attempt["_id"])
        signoffs.append({
            "_id": _oid(),
            "attempt_id": attempt["_id"],
            "caregiver_id": attempt["caregiver_id"],
            "skill_id": attempt["skill_id"],
            "signer": spec["signer"],
            "signer_role": "Care Manager",
            "decision": spec["decision"],
            "override": False,
            "note": spec["note"],
            "at": now.isoformat(),
        })
    if signoffs:
        await db.signoffs.insert_many(list(signoffs))
        await db.attempts.update_many(
            {"_id": {"$in": reviewed_attempt_ids}},
            {"$set": {"reviewed": True}},
        )

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
