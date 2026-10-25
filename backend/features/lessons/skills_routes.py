"""Published-skill endpoints for the lessons feature.

- `GET  /skills/{id}`                              — full skill doc.
- `POST /skills/{id}/edit`                         — copy to a new draft job.
- `PUT  /skills/{id}/translations/{es|tl}`         — save edited translation text.
- `POST /skills/{id}/translations/{es|tl}/review`  — mark as reviewed.
- `POST /skills/{id}/translations/retry`           — re-run translate pipeline.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from db import get_db
from roles import Role, require_role

from .pipeline import utcnow_iso
from .translate import translate_language

logger = logging.getLogger("firstshift.lessons.skills_routes")

router = APIRouter()

# Role gates:
# - archive / unarchive: Care Manager only (destructive on the skill list).
# - edit / translation writes: Care Manager + Trainer.
_ARCHIVE_ROLE = require_role({Role.CARE_MANAGER})
_EDIT_ROLE = require_role({Role.CARE_MANAGER, Role.TRAINER})


def _normalise_lang(lang: str) -> str:
    if lang not in {"es", "tl"}:
        raise HTTPException(status_code=404, detail="language not supported")
    return lang


@router.get("/skills/{skill_id}")
async def get_skill(skill_id: str) -> dict:
    db = get_db()
    doc = await db.skills.find_one({"_id": skill_id})
    if not doc:
        raise HTTPException(status_code=404, detail="skill not found")
    translations = doc.get("translations") or {}
    # Ensure defaults on legacy skills.
    out = {
        "id": doc["_id"],
        "title": doc.get("title") or "",
        "version": int(doc.get("version") or 1),
        "source_credit": doc.get("source_credit") or "",
        "video_id": doc.get("video_id"),
        "archived": bool(doc.get("archived", False)),
        "steps": doc.get("steps") or [],
        "checks": doc.get("checks") or [],
        "quiz": doc.get("quiz") or [],
        "translations": {
            "es": _normalise_translation(translations.get("es")),
            "tl": _normalise_translation(translations.get("tl")),
        },
    }
    return out


def _normalise_translation(t: Any) -> dict:
    if not isinstance(t, dict):
        return {"title": "", "steps": [], "checks": [], "quiz": [], "status": "machine"}
    return {
        "title": t.get("title") or "",
        "steps": t.get("steps") or [],
        "checks": t.get("checks") or [],
        "quiz": t.get("quiz") or [],
        "status": t.get("status") or "machine",
    }


@router.delete("/skills/{skill_id}")
async def archive_skill(skill_id: str, _role: str = Depends(_ARCHIVE_ROLE)) -> dict:
    """Soft-delete: sets `archived: true` on the skill row.

    GET /skills excludes archived by default; GET /skills?include_archived=true
    returns them. No cascade — attempts/signoffs/cleared_skills references stay.
    """
    db = get_db()
    result = await db.skills.update_one(
        {"_id": skill_id},
        {"$set": {"archived": True, "archived_at": utcnow_iso()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="skill not found")
    return {"ok": True, "skill_id": skill_id, "archived": True}


@router.post("/skills/{skill_id}/unarchive")
async def unarchive_skill(skill_id: str, _role: str = Depends(_ARCHIVE_ROLE)) -> dict:
    """Reverse of the archive op (future UI surface)."""
    db = get_db()
    result = await db.skills.update_one(
        {"_id": skill_id},
        {"$set": {"archived": False}, "$unset": {"archived_at": ""}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="skill not found")
    return {"ok": True, "skill_id": skill_id, "archived": False}


@router.post("/skills/{skill_id}/edit")
async def open_edit_job(skill_id: str, _role: str = Depends(_EDIT_ROLE)) -> dict:
    """Lazy edit (Fix #13): return a deterministic `edit-{skill_id}` job_id
    WITHOUT inserting a `lesson_jobs` row. The first `PUT /jobs/{job_id}/draft`
    materialises the row (see `jobs.py::save_draft`). This stops the "I clicked
    Edit three times" drafts drawer from accumulating junk.

    404 if the skill does not exist. Idempotent across repeated clicks and
    across users (same skill_id → same job_id → same resumable editor).
    """
    db = get_db()
    skill = await db.skills.find_one({"_id": skill_id}, {"_id": 1})
    if not skill:
        raise HTTPException(status_code=404, detail="skill not found")
    return {"job_id": f"edit-{skill_id}"}


def _max_end_time(draft: dict) -> float:
    out = 0.0
    for s in draft.get("steps") or []:
        out = max(out, float(s.get("end") or 0.0))
    return round(out, 2)


def _synth_edit_draft(skill: dict) -> dict:
    """Shape a published skill into the lesson_jobs.draft shape so the editor
    can render it even before any row exists in the DB."""
    return {
        "title": skill.get("title") or "",
        "steps": [
            {
                "n": s.get("n"),
                "title": s.get("title") or "",
                "instruction": s.get("instruction") or "",
                "start": float(s.get("start") or 0.0),
                "end": float(s.get("end") or 0.0),
                "frame_id": s.get("frame_id"),
            }
            for s in (skill.get("steps") or [])
        ],
        "checks": [
            {
                "id": c.get("id"),
                "description": c.get("description") or "",
                "safety_critical": bool(c.get("safety_critical", False)),
            }
            for c in (skill.get("checks") or [])
        ],
        "quiz": [
            {
                "id": q.get("id"),
                "prompt": q.get("prompt") or "",
                "choices": list(q.get("choices") or []),
                "answer_index": int(q.get("answer_index") or 0),
            }
            for q in (skill.get("quiz") or [])
        ],
    }


@router.put("/skills/{skill_id}/translations/{lang}")
async def save_translation(
    skill_id: str,
    lang: str,
    body: dict,
    _role: str = Depends(_EDIT_ROLE),
) -> dict:
    """Save manager-edited translation text; status preserved (per spec)."""
    lang = _normalise_lang(lang)
    db = get_db()
    skill = await db.skills.find_one({"_id": skill_id})
    if not skill:
        raise HTTPException(status_code=404, detail="skill not found")
    translations = skill.get("translations") or {}
    current = _normalise_translation(translations.get(lang))

    # Only text fields are editable. Enforce counts/ids match the English.
    new_t = _apply_edited_translation(skill, current, body)

    translations[lang] = new_t
    await db.skills.update_one(
        {"_id": skill_id},
        {"$set": {"translations": translations}},
    )
    return {"ok": True, "translation": new_t}


def _apply_edited_translation(skill: dict, current: dict, body: dict) -> dict:
    """Merge client edits over `current`; preserve ids/n/status (manager edits don't change status)."""
    out = {**current}
    if "title" in body and isinstance(body["title"], str):
        out["title"] = body["title"]

    steps_in = body.get("steps") or []
    if isinstance(steps_in, list) and steps_in:
        by_n = {s.get("n"): s for s in current.get("steps") or []}
        new_steps = []
        for s in skill.get("steps") or []:
            n = s["n"]
            edit = next((x for x in steps_in if x.get("n") == n), None)
            base = by_n.get(n) or {"n": n, "title": s.get("title") or "", "instruction": s.get("instruction") or ""}
            new_steps.append({
                "n": n,
                "title": edit.get("title", base.get("title")) if edit else base.get("title"),
                "instruction": edit.get("instruction", base.get("instruction")) if edit else base.get("instruction"),
            })
        out["steps"] = new_steps

    checks_in = body.get("checks") or []
    if isinstance(checks_in, list) and checks_in:
        by_id = {c.get("id"): c for c in current.get("checks") or []}
        new_checks = []
        for c in skill.get("checks") or []:
            cid = c["id"]
            edit = next((x for x in checks_in if x.get("id") == cid), None)
            base = by_id.get(cid) or {"id": cid, "description": c.get("description") or ""}
            new_checks.append({
                "id": cid,
                "description": edit.get("description", base.get("description")) if edit else base.get("description"),
            })
        out["checks"] = new_checks

    quiz_in = body.get("quiz") or []
    if isinstance(quiz_in, list) and quiz_in:
        by_qid = {q.get("id"): q for q in current.get("quiz") or []}
        new_quiz = []
        for q in skill.get("quiz") or []:
            qid = q["id"]
            edit = next((x for x in quiz_in if x.get("id") == qid), None)
            base = by_qid.get(qid) or {"id": qid, "prompt": q.get("prompt") or "", "choices": list(q.get("choices") or [])}
            prompt = edit.get("prompt", base.get("prompt")) if edit else base.get("prompt")
            choices = edit.get("choices") if edit and isinstance(edit.get("choices"), list) else base.get("choices")
            new_quiz.append({"id": qid, "prompt": prompt, "choices": [str(x) for x in (choices or [])[:3]]})
        out["quiz"] = new_quiz
    # Status preserved.
    return out


@router.post("/skills/{skill_id}/translations/{lang}/review")
async def review_translation(
    skill_id: str,
    lang: str,
    _role: str = Depends(_EDIT_ROLE),
) -> dict:
    lang = _normalise_lang(lang)
    db = get_db()
    skill = await db.skills.find_one({"_id": skill_id})
    if not skill:
        raise HTTPException(status_code=404, detail="skill not found")
    translations = skill.get("translations") or {}
    t = _normalise_translation(translations.get(lang))
    t["status"] = "reviewed"
    translations[lang] = t
    await db.skills.update_one({"_id": skill_id}, {"$set": {"translations": translations}})
    return {"ok": True, "status": "reviewed"}


@router.post("/skills/{skill_id}/translations/retry")
async def retry_translations(skill_id: str, _role: str = Depends(_EDIT_ROLE)) -> dict:
    """Re-run the translate pipeline for es+tl."""
    db = get_db()
    skill = await db.skills.find_one({"_id": skill_id})
    if not skill:
        raise HTTPException(status_code=404, detail="skill not found")

    english_for_lang = {
        "title": skill.get("title") or "",
        "steps": [{"n": s["n"], "title": s.get("title") or "", "instruction": s.get("instruction") or ""} for s in (skill.get("steps") or [])],
        "checks": [{"id": c["id"], "description": c.get("description") or ""} for c in (skill.get("checks") or [])],
        "quiz": [{"id": q["id"], "prompt": q.get("prompt") or "", "choices": list(q.get("choices") or [])} for q in (skill.get("quiz") or [])],
    }

    translations = skill.get("translations") or {}
    out: dict[str, Any] = {}
    for lang in ("es", "tl"):
        prior = translations.get(lang)
        if isinstance(prior, dict) and prior.get("status") == "stale":
            prior = None  # force full retranslate; our diff considers "no prior" ⇒ all changed
        # Retry has no "prior english" concept (we're redoing the current English); force full retranslate.
        payload, status = await translate_language(
            english=english_for_lang,
            prior_english=None,
            prior_lang=prior,
            lang=lang,
        )
        payload["status"] = status
        out[lang] = payload
    await db.skills.update_one({"_id": skill_id}, {"$set": {"translations": out}})
    return {"ok": True, "translations": out}
