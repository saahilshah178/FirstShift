"""Job + draft endpoints for the lessons feature.

- `GET  /jobs`                                — list drafts & in-progress jobs.
- `GET  /jobs/{job_id}`                       — single job detail.
- `POST /jobs/{job_id}/retry`                 — resume from first missing stage.
- `PUT  /jobs/{job_id}/draft`                 — save edits + re-validate.
- `POST /jobs/{job_id}/steps/{n}/frame`       — regenerate a frame.
- `POST /jobs/{job_id}/publish`               — atomic ready → publishing, write skill, translate.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from db import get_db

from .pipeline import regen_single_frame, utcnow_iso
from .runner import kick_job, sweep_stale_jobs
from .schemas import blocking_problems, validate_analyze
from .translate import translate_language

logger = logging.getLogger("firstshift.lessons.jobs")

router = APIRouter()

# Fix #13 lazy edit — a job_id of the form `edit-{skill_id}` is a deterministic
# edit "handle" that does NOT have a `lesson_jobs` row until the first save.
EDIT_PREFIX = "edit-"


def _edit_skill_id(job_id: str) -> str | None:
    """Return the underlying skill_id if `job_id` is a lazy edit handle."""
    if isinstance(job_id, str) and job_id.startswith(EDIT_PREFIX):
        return job_id[len(EDIT_PREFIX):]
    return None


def _synth_job_from_skill(job_id: str, skill: dict) -> dict:
    """Build an in-memory job doc from a published skill (no DB insert)."""
    from .skills_routes import _synth_edit_draft  # avoid cycle at import time

    draft = _synth_edit_draft(skill)
    duration_s = 0.0
    for s in draft.get("steps") or []:
        duration_s = max(duration_s, float(s.get("end") or 0.0))
    return {
        "_id": job_id,
        "status": "ready",
        "error": "",
        "video_id": skill.get("video_id"),
        "source_credit": skill.get("source_credit") or "",
        "skill_id": skill["_id"],
        "duration_s": round(duration_s, 2),
        "draft": draft,
        "problems": [],
        "draft_rev": 0,
        "heartbeat_at": utcnow_iso(),
        "created_at": utcnow_iso(),
        "updated_at": utcnow_iso(),
    }


def _job_public(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "status": doc.get("status"),
        "error": doc.get("error") or "",
        "video_id": doc.get("video_id"),
        "source_credit": doc.get("source_credit") or "",
        "skill_id": doc.get("skill_id"),
        "duration_s": doc.get("duration_s") or 0.0,
        "draft": doc.get("draft") or {"title": "", "steps": [], "checks": [], "quiz": []},
        "problems": doc.get("problems") or [],
        "draft_rev": int(doc.get("draft_rev") or 0),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


@router.get("/jobs")
async def list_jobs() -> dict:
    await sweep_stale_jobs()  # lazy sweep
    db = get_db()
    cursor = db.lesson_jobs.find(
        # Everything but 'published' (so the drafts area shows active + failed + ready).
        {"status": {"$ne": "published"}}
    ).sort("updated_at", -1)
    jobs = [_job_public(d) async for d in cursor]
    return {"jobs": jobs}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    await sweep_stale_jobs()  # lazy sweep
    db = get_db()
    doc = await db.lesson_jobs.find_one({"_id": job_id})
    # Fix #13 — a lazy edit handle (`edit-{skill_id}`) always presents a
    # fresh editor view. If a prior session finished at `published`, that
    # row is a terminal breadcrumb; synthesize a new virgin draft from the
    # current skill so the next Edit click starts clean (no "already
    # published" dead-ends in the UI).
    skill_id = _edit_skill_id(job_id)
    if doc and skill_id and doc.get("status") == "published":
        doc = None
    if doc:
        return _job_public(doc)
    if skill_id:
        skill = await db.skills.find_one({"_id": skill_id})
        if not skill:
            raise HTTPException(status_code=404, detail="skill not found")
        return _job_public(_synth_job_from_skill(job_id, skill))
    raise HTTPException(status_code=404, detail="job not found")


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str) -> dict:
    db = get_db()
    doc = await db.lesson_jobs.find_one({"_id": job_id})
    if not doc:
        raise HTTPException(status_code=404, detail="job not found")
    if doc.get("status") in {"published"}:
        raise HTTPException(status_code=409, detail="job is already published")
    # Reset error, heartbeat the row so a stale sweep doesn't immediately flip it.
    await db.lesson_jobs.update_one(
        {"_id": job_id},
        {"$set": {
            "error": "",
            "heartbeat_at": utcnow_iso(),
            "updated_at": utcnow_iso(),
        }, "$inc": {"draft_rev": 1}},
    )
    # If we never produced a video_id, we need the assembled file — gone after original run.
    # In that case the runner itself will raise; we surface that failure.
    kick_job(job_id, assembled_path=None)
    return {"ok": True}


@router.put("/jobs/{job_id}/draft")
async def save_draft(job_id: str, body: dict) -> dict:
    """Save editor changes, re-run validation, return problems.

    Fix #13 — if `job_id` is a lazy edit handle (`edit-{skill_id}`) and no
    `lesson_jobs` row exists yet (or the only row is a terminal `published`
    breadcrumb from a prior session), materialise a fresh one using the
    published skill as the base. All subsequent saves update normally.
    """
    db = get_db()
    doc = await db.lesson_jobs.find_one({"_id": job_id})
    skill_id = _edit_skill_id(job_id)
    if doc and skill_id and doc.get("status") == "published":
        # Replace the terminal breadcrumb with a virgin edit row.
        await db.lesson_jobs.delete_one({"_id": job_id})
        doc = None
    if not doc:
        if not skill_id:
            raise HTTPException(status_code=404, detail="job not found")
        skill = await db.skills.find_one({"_id": skill_id})
        if not skill:
            raise HTTPException(status_code=404, detail="skill not found")
        if int(body.get("draft_rev") or 0) != 0:
            raise HTTPException(status_code=409, detail="draft_rev stale (job not yet created; expected 0)")
        synth = _synth_job_from_skill(job_id, skill)
        await db.lesson_jobs.insert_one(synth)
        doc = synth
    if doc.get("status") == "published":
        raise HTTPException(status_code=409, detail="published; use /skills/{id}/edit")

    incoming_rev = int(body.get("draft_rev") or 0)
    current_rev = int(doc.get("draft_rev") or 0)
    if incoming_rev != current_rev:
        raise HTTPException(status_code=409, detail=f"draft_rev stale (got {incoming_rev}, have {current_rev})")

    new_draft = body.get("draft") or {}
    source_credit = (body.get("source_credit") or doc.get("source_credit") or "").strip()
    duration_s = float(doc.get("duration_s") or 0.0)

    # Preserve frame_ids: validation strips them, re-attach from the client payload.
    client_steps = {s.get("n"): s for s in (new_draft.get("steps") or [])}
    # Build a shape the validator expects (title, steps, checks, quiz).
    probe_payload = {
        "title": new_draft.get("title"),
        "steps": [
            {
                "n": s.get("n"),
                "title": s.get("title"),
                "instruction": s.get("instruction"),
                "start": s.get("start"),
                "end": s.get("end"),
            }
            for s in (new_draft.get("steps") or [])
        ],
        "checks": [
            {
                "id": c.get("id"),
                "description": c.get("description"),
                "safety_critical": c.get("safety_critical"),
            }
            for c in (new_draft.get("checks") or [])
        ],
        "quiz": [
            {
                "q": q.get("prompt") or q.get("q"),
                "options": q.get("choices") or q.get("options") or [],
                "answer": q.get("answer_index") if q.get("answer_index") is not None else q.get("answer"),
            }
            for q in (new_draft.get("quiz") or [])
        ],
    }
    validated_draft, problems = validate_analyze(probe_payload, duration_s)
    # Re-attach frame_ids from the client payload (validator wipes them to None).
    for step in validated_draft["steps"]:
        src = client_steps.get(step["n"])
        if src and src.get("frame_id"):
            step["frame_id"] = src["frame_id"]

    await db.lesson_jobs.update_one(
        {"_id": job_id},
        {"$set": {
            "draft": validated_draft,
            "problems": problems,
            "source_credit": source_credit,
            "updated_at": utcnow_iso(),
            "heartbeat_at": utcnow_iso(),
        }, "$inc": {"draft_rev": 1}},
    )
    out = await db.lesson_jobs.find_one({"_id": job_id})
    return _job_public(out)


@router.post("/jobs/{job_id}/steps/{n}/frame")
async def regen_frame(job_id: str, n: int) -> dict:
    db = get_db()
    doc = await db.lesson_jobs.find_one({"_id": job_id})
    skill_id = _edit_skill_id(job_id)
    if doc and skill_id and doc.get("status") == "published":
        await db.lesson_jobs.delete_one({"_id": job_id})
        doc = None
    if not doc:
        # Fix #13 — same lazy materialisation story as save_draft.
        if not skill_id:
            raise HTTPException(status_code=404, detail="job not found")
        skill = await db.skills.find_one({"_id": skill_id})
        if not skill:
            raise HTTPException(status_code=404, detail="skill not found")
        synth = _synth_job_from_skill(job_id, skill)
        await db.lesson_jobs.insert_one(synth)
        doc = synth
    if not doc.get("video_id"):
        raise HTTPException(status_code=409, detail="no video to extract from yet")
    steps = (doc.get("draft") or {}).get("steps") or []
    step = next((s for s in steps if int(s.get("n") or 0) == int(n)), None)
    if not step:
        raise HTTPException(status_code=404, detail="step not found")
    frame_id = await regen_single_frame(doc["video_id"], step.get("start") or 0.0, step.get("end") or 0.0)
    # Save frame_id back onto the step.
    new_steps = [
        {**s, "frame_id": frame_id} if int(s.get("n") or 0) == int(n) else s
        for s in steps
    ]
    new_draft = {**(doc.get("draft") or {}), "steps": new_steps}
    await db.lesson_jobs.update_one(
        {"_id": job_id},
        {"$set": {
            "draft": new_draft,
            "updated_at": utcnow_iso(),
            "heartbeat_at": utcnow_iso(),
        }, "$inc": {"draft_rev": 1}},
    )
    return {"ok": True, "step": {"n": n, "frame_id": frame_id}}


@router.post("/jobs/{job_id}/publish")
async def publish_job(job_id: str) -> dict:
    """Idempotent publish. Atomic ready → publishing to prevent double-fire.

    Fix #13 — if `job_id` is a lazy edit handle with no `lesson_jobs` row
    yet (i.e. the user clicked Edit but changed nothing), reject with 422
    rather than publishing a vacuous version bump. The "already published"
    breadcrumb for a lazy handle counts the same way — nothing new to publish.
    """
    db = get_db()
    doc = await db.lesson_jobs.find_one({"_id": job_id})
    skill_id = _edit_skill_id(job_id)
    if (
        skill_id
        and (not doc or doc.get("status") == "published")
    ):
        raise HTTPException(
            status_code=422,
            detail={"reasons": ["No changes to publish — edit something first."]},
        )
    if not doc:
        raise HTTPException(status_code=404, detail="job not found")

    # Validate publish-readiness (422 with reasons).
    reasons = _publish_blockers(doc)
    if reasons:
        raise HTTPException(status_code=422, detail={"reasons": reasons})

    # Atomic ready → publishing. If we don't match, we're not in a state we can publish from.
    atomic = await db.lesson_jobs.update_one(
        {"_id": job_id, "status": "ready"},
        {"$set": {"status": "publishing", "error": "", "updated_at": utcnow_iso(), "heartbeat_at": utcnow_iso()},
         "$inc": {"draft_rev": 1}},
    )
    if atomic.modified_count == 0:
        # Reload and tell the caller.
        current = await db.lesson_jobs.find_one({"_id": job_id})
        state = (current or {}).get("status")
        if state == "publishing":
            raise HTTPException(status_code=409, detail="publish already in progress")
        if state == "published":
            raise HTTPException(status_code=409, detail="already published")
        raise HTTPException(status_code=409, detail=f"not publishable (status={state})")

    try:
        # ---- Build the skill doc ----
        draft = doc.get("draft") or {}
        existing_skill_id = doc.get("skill_id")
        existing_skill = None
        if existing_skill_id:
            existing_skill = await db.skills.find_one({"_id": existing_skill_id})

        skill_id = existing_skill_id or uuid.uuid4().hex
        next_version = int((existing_skill or {}).get("version") or 0) + 1 if existing_skill else 1

        # English stays as-is (not translated here).
        english = {
            "title": draft.get("title") or "",
            "steps": [
                {
                    "n": s["n"],
                    "title": s.get("title") or "",
                    "instruction": s.get("instruction") or "",
                    "start": float(s.get("start") or 0.0),
                    "end": float(s.get("end") or 0.0),
                    "frame_id": s.get("frame_id"),
                }
                for s in (draft.get("steps") or [])
            ],
            "checks": [
                {
                    "id": c["id"],
                    "description": c.get("description") or "",
                    "safety_critical": bool(c.get("safety_critical", False)),
                }
                for c in (draft.get("checks") or [])
            ],
            "quiz": [
                {
                    "id": q["id"],
                    "prompt": q.get("prompt") or "",
                    "choices": [str(x) for x in (q.get("choices") or [])],
                    "answer_index": int(q.get("answer_index") or 0),
                }
                for q in (draft.get("quiz") or [])
            ],
        }

        # Translate (idempotent re: unchanged items).
        import os as _os
        force = _os.environ.get("LESSONS_FORCE_FAIL_STAGE", "")
        if force == "publishing":
            raise RuntimeError("forced failure (LESSONS_FORCE_FAIL_STAGE=publishing)")

        prior_translations = (existing_skill or {}).get("translations") or {}
        prior_english = None
        if existing_skill:
            prior_english = {
                "title": existing_skill.get("title") or "",
                "steps": [{"n": s["n"], "title": s.get("title") or "", "instruction": s.get("instruction") or ""} for s in (existing_skill.get("steps") or [])],
                "checks": [{"id": c["id"], "description": c.get("description") or ""} for c in (existing_skill.get("checks") or [])],
                "quiz": [{"id": q["id"], "prompt": q.get("prompt") or "", "choices": list(q.get("choices") or [])} for q in (existing_skill.get("quiz") or [])],
            }
        translations_out: dict[str, Any] = {}
        for lang in ("es", "tl"):
            prior = prior_translations.get(lang)
            # Build an english+ids payload matching translation shape (no answer_index/safety_critical).
            english_for_lang = {
                "title": english["title"],
                "steps": [{"n": s["n"], "title": s["title"], "instruction": s["instruction"]} for s in english["steps"]],
                "checks": [{"id": c["id"], "description": c["description"]} for c in english["checks"]],
                "quiz": [{"id": q["id"], "prompt": q["prompt"], "choices": list(q["choices"])} for q in english["quiz"]],
            }
            payload, status = await translate_language(
                english=english_for_lang,
                prior_english=prior_english,
                prior_lang=prior,
                lang=lang,
            )
            payload["status"] = status
            translations_out[lang] = payload

        skill_doc = {
            "_id": skill_id,
            "title": english["title"],
            "steps": english["steps"],
            "checks": english["checks"],
            "quiz": english["quiz"],
            "version": next_version,
            # Fix #13 — source_credit preservation: if the draft/editor
            # left it blank, keep whatever the previously-published skill
            # had rather than silently clearing it.
            "source_credit": (
                (doc.get("source_credit") or "").strip()
                or ((existing_skill or {}).get("source_credit") or "")
            ),
            "video_id": doc.get("video_id") or (existing_skill or {}).get("video_id"),
            "translations": translations_out,
        }
        await db.skills.replace_one({"_id": skill_id}, skill_doc, upsert=True)

        await db.lesson_jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "published",
                "skill_id": skill_id,
                "error": "",
                "updated_at": utcnow_iso(),
                "heartbeat_at": utcnow_iso(),
            }, "$inc": {"draft_rev": 1}},
        )
        # Fix #13 — after a successful publish, drop ALL draft rows that
        # target this skill_id, including the one that just published.
        # Rationale: the published skill IS the audit trail; the editor is
        # a lazy handle (`edit-{skill_id}`) that should start virgin on the
        # next click. Rows with status `published` for OTHER skill_ids are
        # untouched (that's unrelated history).
        wipe = await db.lesson_jobs.delete_many({"skill_id": skill_id})
        if wipe.deleted_count > 1:
            logger.info(
                "publish %s: wiped %d draft row(s) for skill %s (self + siblings)",
                job_id, wipe.deleted_count, skill_id,
            )
        return {"skill_id": skill_id, "version": next_version}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("publish failed for job %s: %s", job_id, exc)
        msg = (str(exc).splitlines()[0] or "publish failed")[:300]
        # Rewind to ready so the user can try again.
        await db.lesson_jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "ready",
                "error": msg,
                "updated_at": utcnow_iso(),
                "heartbeat_at": utcnow_iso(),
            }, "$inc": {"draft_rev": 1}},
        )
        raise HTTPException(status_code=500, detail=msg) from exc


def _publish_blockers(doc: dict) -> list[str]:
    """Return human reasons that block publish; empty when it's safe.

    Fix #10 — quiz count is now unconstrained (0..N allowed). Each
    quiz question that IS present still needs 3 valid choices and a
    valid answer index (0..2).
    """
    reasons: list[str] = []
    draft = doc.get("draft") or {}
    steps = draft.get("steps") or []
    checks = draft.get("checks") or []
    quiz = draft.get("quiz") or []
    if not steps:
        reasons.append("At least one step is required.")
    for s in steps:
        if not s.get("frame_id"):
            reasons.append(f"Step {s.get('n')} is missing a frame.")
            break
    if not checks:
        reasons.append("At least one check is required.")
    for q in quiz:
        if len(q.get("choices") or []) != 3:
            reasons.append("Each quiz question needs 3 choices.")
            break
        ai = q.get("answer_index")
        if not isinstance(ai, int) or ai < 0 or ai > 2:
            reasons.append("Each quiz question needs a valid correct answer (1..3).")
            break
    # Any blocking problems from the draft itself.
    for p in blocking_problems(doc.get("problems") or []):
        reasons.append(f"{p.get('where')}: {p.get('message')}")
    return reasons
