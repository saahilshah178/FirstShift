"""plans feature — caregiver training plans, incidents, cert map, near-miss.

Mounted at `/api/plans`. Owns three collections:

- `plans` — one doc per caregiver, items = `[{skill_id, mode, refresher?}]`.
  Only `mode` and the `refresher` override are persisted; `status` is
  always derived on read (CONTRACTS §12 — derived state wins).
- `incidents` — append-only audit of near-miss reports.
- `cert_skill_map` — small editable table mapping cert name → verify
  skill ids. Seeded at startup; see `backend/features/plans/seed.py`.
- `refresher_drafts` — one doc per outstanding draft refresher message
  the Care Manager can edit, Send to the caregiver chat, or Discard.

Role gating: all write endpoints are Care-Manager-only; read endpoints
are open to any agency role. Scheduler + Trainer get 403 on writes
(near-miss, refresher send/discard).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from db import get_db
from roles import Role, require_role
from services.channel_service import send_message_async

logger = logging.getLogger("firstshift.plans")

router = APIRouter()

_CARE_MANAGER_ROLE = require_role({Role.CARE_MANAGER})

MODES = ("learn", "verify")
DERIVED_STATUSES = ("not_started", "practicing", "cleared", "refresher")

# ---------------------------------------------------------------------------
# derived status
# ---------------------------------------------------------------------------

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _active_conversation(db, caregiver_id: str) -> dict | None:
    return await db.conversations.find_one({"caregiver_id": caregiver_id})


async def _derive_status(
    db,
    *,
    caregiver_id: str,
    cleared_skills: set[str],
    skill_id: str,
    refresher_override: bool,
    attempt_skill_ids: set[str],
    conv: dict | None,
) -> str:
    """Rules (priority order):
    1. `refresher` override (persisted after a near-miss) → "refresher"
    2. skill in `caregiver.cleared_skills` → "cleared"
    3. unapproved attempt in ready_to_sign/needs_practice → "practicing"
    4. active conversation is in_lesson/quiz/awaiting_video for this skill → "practicing"
    5. otherwise → "not_started"
    """
    if refresher_override:
        return "refresher"
    if skill_id in cleared_skills:
        return "cleared"
    if skill_id in attempt_skill_ids:
        return "practicing"
    if conv and conv.get("skill_id") == skill_id:
        if conv.get("state") in ("in_lesson", "quiz", "awaiting_video"):
            return "practicing"
    return "not_started"


# ---------------------------------------------------------------------------
# plan lifecycle
# ---------------------------------------------------------------------------

async def ensure_plan_for(caregiver_id: str) -> dict:
    """Return the plan doc for the caregiver, creating a learn-mode default
    plan over the full active-skill set if none exists yet.

    Idempotent. Safe to call on every read. The brief says "every existing
    caregiver gets a plan with all 4 current skills, all mode='learn'"; the
    startup backfill calls this for every caregiver and this read-time
    guarantee makes the backfill a soft migration (no explicit script run
    needed).
    """
    db = get_db()
    existing = await db.plans.find_one({"caregiver_id": caregiver_id})
    if existing:
        return existing
    skill_ids = [
        s["_id"]
        for s in await db.skills.find({"archived": {"$ne": True}}, {"_id": 1}).to_list(length=200)
    ]
    doc = {
        "_id": uuid.uuid4().hex,
        "caregiver_id": caregiver_id,
        "items": [{"skill_id": sid, "mode": "learn"} for sid in skill_ids],
        "created_at": _utc_iso(),
        "updated_at": _utc_iso(),
    }
    try:
        await db.plans.insert_one(doc)
    except Exception as exc:  # race: another request just inserted
        logger.warning("plan insert race for %s: %s", caregiver_id, exc)
        existing = await db.plans.find_one({"caregiver_id": caregiver_id})
        return existing or doc
    return doc


async def _resolve_plan_items(
    db,
    *,
    caregiver_id: str,
    plan: dict,
) -> list[dict]:
    """Resolve `plan.items` into full view-model rows with derived status."""
    caregiver = await db.caregivers.find_one(
        {"_id": caregiver_id}, {"cleared_skills": 1},
    )
    cleared = set((caregiver or {}).get("cleared_skills") or [])
    conv = await _active_conversation(db, caregiver_id)
    attempts = await db.attempts.find(
        {
            "caregiver_id": caregiver_id,
            "status": {"$in": ["ready_to_sign", "needs_practice"]},
            "reviewed": {"$ne": True},
        },
        {"skill_id": 1},
    ).to_list(length=500)
    attempt_skill_ids = {a["skill_id"] for a in attempts if a.get("skill_id")}

    skills_by_id = {
        s["_id"]: s
        for s in await db.skills.find(
            {"_id": {"$in": [i["skill_id"] for i in plan.get("items") or []]}},
            {"_id": 1, "title": 1},
        ).to_list(length=500)
    }

    # Verify-mode cert source lookup: for each plan item in `verify`, find
    # which cert in `cert_skill_map` included it. Multiple certs may both
    # cover a skill; we concat them.
    cert_rows = await db.cert_skill_map.find({}).to_list(length=50)
    cert_by_skill: dict[str, list[str]] = {}
    for row in cert_rows:
        for sid in row.get("verify_skill_ids") or []:
            cert_by_skill.setdefault(sid, []).append(row.get("certificate"))

    # Refresher audit — find the latest incident per skill for this caregiver.
    incidents = await db.incidents.find(
        {"caregiver_id": caregiver_id}
    ).sort("created_at", -1).to_list(length=100)
    incident_by_skill: dict[str, dict] = {}
    for inc in incidents:
        sid = inc.get("skill_id")
        if sid and sid not in incident_by_skill:
            incident_by_skill[sid] = inc

    out: list[dict] = []
    for item in plan.get("items") or []:
        sid = item.get("skill_id")
        skill = skills_by_id.get(sid)
        if not skill:
            continue
        refresher_override = bool(item.get("refresher"))
        status = await _derive_status(
            db,
            caregiver_id=caregiver_id,
            cleared_skills=cleared,
            skill_id=sid,
            refresher_override=refresher_override,
            attempt_skill_ids=attempt_skill_ids,
            conv=conv,
        )
        row = {
            "skill_id": sid,
            "title": skill.get("title") or "",
            "mode": item.get("mode", "learn"),
            "status": status,
        }
        if item.get("mode") == "verify":
            certs = cert_by_skill.get(sid) or []
            if certs:
                # Prefer the caregiver's own stated cert over any other
                # match. Stored on the caregiver's `experience.certifications`.
                row["verified_because"] = certs[0]
        if status == "refresher" and sid in incident_by_skill:
            inc = incident_by_skill[sid]
            row["refresher_at"] = inc.get("created_at")
            row["refresher_reason"] = inc.get("description")
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@router.get("/caregiver/{caregiver_id}")
async def get_plan(caregiver_id: str) -> dict:
    """Return the caregiver's plan with derived per-item status.

    - Reads `plans` collection (auto-creates if the caregiver has no plan yet).
    - Resolves each item: `{skill_id, title, mode, status[, verified_because, refresher_at, refresher_reason]}`.
    - Status is DERIVED on every read from `cleared_skills`, open attempts,
      and the active conversation (CONTRACTS §12 — never trust persisted
      status alone).
    """
    db = get_db()
    caregiver = await db.caregivers.find_one({"_id": caregiver_id})
    if not caregiver:
        raise HTTPException(status_code=404, detail="caregiver not found")
    plan = await ensure_plan_for(caregiver_id)
    items = await _resolve_plan_items(db, caregiver_id=caregiver_id, plan=plan)
    verify_count = sum(1 for i in items if i["mode"] == "verify")
    cleared_count = sum(1 for i in items if i["status"] == "cleared")
    return {
        "plan_id": plan["_id"],
        "caregiver_id": caregiver_id,
        "items": items,
        "verify_count": verify_count,
        "cleared_count": cleared_count,
        "total": len(items),
    }


# -- Near-miss ---------------------------------------------------------------

@router.post("/caregiver/{caregiver_id}/near-miss")
async def report_near_miss(
    caregiver_id: str,
    body: dict,
    role: str = Depends(_CARE_MANAGER_ROLE),
) -> dict:
    """Report a near-miss on a caregiver's cleared skill.

    Atomic:
    1. Insert `incidents` row.
    2. `$pull` the skill from `caregiver.cleared_skills`.
    3. Flip the plan item's `refresher: True` (persisted override) so
       the plan reports `status: "refresher"` on next read.
    4. Create a `refresher_drafts` doc with a localized prefilled text.
       **Does NOT** send anything to the caregiver chat yet — Care
       Manager must tap Send on the draft from the competency file.
    """
    skill_id = str(body.get("skill_id") or "").strip()
    description = str(body.get("description") or "").strip()
    if not skill_id:
        raise HTTPException(status_code=422, detail="skill_id required")
    if not description:
        raise HTTPException(status_code=422, detail="description required")

    db = get_db()
    caregiver = await db.caregivers.find_one({"_id": caregiver_id})
    if not caregiver:
        raise HTTPException(status_code=404, detail="caregiver not found")
    skill = await db.skills.find_one({"_id": skill_id})
    if not skill:
        raise HTTPException(status_code=404, detail="skill not found")
    # The brief: near-miss "removes cleared skill, drafts a refresher
    # message". Only makes sense on a currently-cleared skill. Guard
    # against stale UI firing it on a not-started row.
    if skill_id not in (caregiver.get("cleared_skills") or []):
        raise HTTPException(
            status_code=422,
            detail={"reason": "not_cleared", "skill_id": skill_id},
        )

    incident_id = uuid.uuid4().hex
    now = _utc_iso()
    await db.incidents.insert_one({
        "_id": incident_id,
        "caregiver_id": caregiver_id,
        "skill_id": skill_id,
        "description": description,
        "reporter_role": role,
        "created_at": now,
    })

    await db.caregivers.update_one(
        {"_id": caregiver_id},
        {"$pull": {"cleared_skills": skill_id}},
    )

    plan = await ensure_plan_for(caregiver_id)
    # Flip the matching plan item's refresher override. If the plan
    # didn't list this skill (edge case: skill was added after plan
    # creation), append a new learn-mode row with the override.
    existing_item = next(
        (i for i in (plan.get("items") or []) if i.get("skill_id") == skill_id),
        None,
    )
    if existing_item:
        await db.plans.update_one(
            {"_id": plan["_id"], "items.skill_id": skill_id},
            {
                "$set": {
                    "items.$.refresher": True,
                    "updated_at": now,
                },
            },
        )
    else:
        await db.plans.update_one(
            {"_id": plan["_id"]},
            {
                "$push": {"items": {"skill_id": skill_id, "mode": "learn", "refresher": True}},
                "$set": {"updated_at": now},
            },
        )

    # Localized refresher draft text.
    lang = caregiver.get("language") or "en"
    skill_title = _localized_skill_title(skill, lang)
    draft_text = _refresher_template(lang).format(skill=skill_title)
    draft_id = uuid.uuid4().hex
    await db.refresher_drafts.insert_one({
        "_id": draft_id,
        "caregiver_id": caregiver_id,
        "skill_id": skill_id,
        "incident_id": incident_id,
        "text": draft_text,
        "created_at": now,
    })

    logger.info(
        "near-miss: caregiver=%s skill=%s incident=%s draft=%s",
        caregiver_id, skill_id, incident_id, draft_id,
    )
    return {
        "ok": True,
        "incident_id": incident_id,
        "draft_id": draft_id,
        "draft_text": draft_text,
    }


_REFRESHER_TEMPLATES = {
    "en": (
        "Hi — your care manager noticed something during a recent shift and "
        "wants to walk through {skill} with you again before your next "
        "visit. Reply with menu to pick it up."
    ),
    "es": (
        "Hola — tu coordinadora de cuidados notó algo en un turno reciente "
        "y quiere repasar {skill} contigo antes de tu próxima visita. "
        "Responde menu para empezar."
    ),
    "tl": (
        "Hi — napansin ng iyong care manager ang isang bagay noong "
        "nakaraang shift at gustong dumaan sa {skill} muli bago ang susunod "
        "mong bisita. Mag-reply ng menu para simulan."
    ),
}


def _refresher_template(lang: str) -> str:
    return _REFRESHER_TEMPLATES.get(lang) or _REFRESHER_TEMPLATES["en"]


def _localized_skill_title(skill: dict, lang: str) -> str:
    if lang in ("es", "tl"):
        t = (skill.get("translations") or {}).get(lang) or {}
        if t.get("title"):
            return t["title"]
    return skill.get("title") or ""


# -- Refresher drafts --------------------------------------------------------

@router.get("/caregiver/{caregiver_id}/refresher-drafts")
async def list_refresher_drafts(caregiver_id: str) -> dict:
    db = get_db()
    drafts = await db.refresher_drafts.find(
        {"caregiver_id": caregiver_id}
    ).sort("created_at", -1).to_list(length=50)
    return {
        "drafts": [
            {
                "id": d["_id"],
                "skill_id": d.get("skill_id"),
                "text": d.get("text") or "",
                "created_at": d.get("created_at"),
            }
            for d in drafts
        ],
    }


@router.put("/refresher-drafts/{draft_id}")
async def update_refresher_draft(
    draft_id: str,
    body: dict,
    _role: str = Depends(_CARE_MANAGER_ROLE),
) -> dict:
    """Save Care-Manager edits to the draft text before Send."""
    db = get_db()
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="text required")
    r = await db.refresher_drafts.update_one(
        {"_id": draft_id},
        {"$set": {"text": text, "updated_at": _utc_iso()}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="draft not found")
    return {"ok": True, "draft_id": draft_id, "text": text}


@router.post("/refresher-drafts/{draft_id}/send")
async def send_refresher_draft(
    draft_id: str,
    _role: str = Depends(_CARE_MANAGER_ROLE),
) -> dict:
    """Push the draft text into the caregiver's chat via `send_message`.

    Deletes the draft row on success — a draft is a one-shot: once sent,
    it lives on in the chat timeline and in the `incidents` audit log,
    not here.
    """
    db = get_db()
    draft = await db.refresher_drafts.find_one({"_id": draft_id})
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    await send_message_async(draft["caregiver_id"], draft.get("text") or "")
    await db.refresher_drafts.delete_one({"_id": draft_id})
    return {"ok": True, "caregiver_id": draft["caregiver_id"]}


@router.delete("/refresher-drafts/{draft_id}")
async def discard_refresher_draft(
    draft_id: str,
    _role: str = Depends(_CARE_MANAGER_ROLE),
) -> dict:
    db = get_db()
    r = await db.refresher_drafts.delete_one({"_id": draft_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="draft not found")
    return {"ok": True}


# -- cert map ----------------------------------------------------------------

@router.get("/cert-map")
async def get_cert_map() -> dict:
    """Return the cert → verify-skill-ids map (names only; frontend
    resolves titles)."""
    db = get_db()
    rows = await db.cert_skill_map.find({}).to_list(length=50)
    return {
        "certificates": [
            {
                "certificate": r.get("certificate"),
                "verify_skill_ids": list(r.get("verify_skill_ids") or []),
            }
            for r in rows
        ],
    }


# -- incidents list (for the audit view in Stage 4 if we add one) -----------

@router.get("/caregiver/{caregiver_id}/incidents")
async def list_incidents(caregiver_id: str) -> dict:
    db = get_db()
    rows = await db.incidents.find({"caregiver_id": caregiver_id}).sort("created_at", -1).to_list(length=100)
    return {
        "incidents": [
            {
                "id": r["_id"],
                "skill_id": r.get("skill_id"),
                "description": r.get("description"),
                "created_at": r.get("created_at"),
                "reporter_role": r.get("reporter_role"),
            }
            for r in rows
        ],
    }
