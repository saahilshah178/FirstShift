"""Caregiver-channel state machine.

Single entry point `handle_inbound(caregiver_id, text, media_id, channel)` drives
the conversation forward. Pure data in, side-effects via
`services.channel_service.send_message_async` + the grading ingest helpers.

States live on the `conversations` collection (one doc per caregiver):
  idle | in_lesson | quiz | awaiting_video | awaiting_result
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

from db import get_db

from services.channel_service import send_message_async

logger = logging.getLogger("firstshift.channel.state_machine")


# ---------- language helpers ----------
_PROMPT_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "Hi {first_name}! I'm your training coach. Reply with the number of a skill to practice:",
        "menu_header": "Skills to practice:",
        "menu_item": "{n}. {title}",
        "menu_prompt": "Reply with a number to start.",
        "unknown_menu": "I didn't catch that. Reply with the number of a skill:",
        "none_remaining": "You've cleared every skill — nice work.",
        "step_header": "Step {n}/{total}: {title}",
        "step_safety_en_hint": "⚠ Safety-critical. In English: {en}",
        "step_next_hint": "Reply with anything to continue.",
        "step_next_button": "Next",
        "quiz_header": "Quiz question {n}/{total}: {prompt}",
        "quiz_opt": "{num}. {text}",
        "quiz_prompt": "Reply 1, 2, or 3.",
        "quiz_prompt_invalid": "Please answer 1, 2, or 3.",
        "quiz_correct": "Correct ✓",
        "quiz_wrong": "Not quite. The answer is: {num}",
        "video_request": "Last step: send a practice video, under 45 seconds.",
        "checking_video": "Checking your video…",
        "still_checking": "Still checking…",
        "result_pass": "Nice — sent to your nurse for sign-off.",
        "result_missed": "Missed: {desc} at {t}.",
        "result_retry": "Please try again. {msg}",
        "result_retake": "Please try again from the top. {msg}",
        "result_error": "Something went wrong grading your video. Please try again.",
    },
    "es": {
        "welcome": "¡Hola {first_name}! Soy tu coach de capacitación. Responde con el número de la habilidad para practicar:",
        "menu_header": "Habilidades para practicar:",
        "menu_item": "{n}. {title}",
        "menu_prompt": "Responde con un número para empezar.",
        "unknown_menu": "No entendí. Responde con el número de la habilidad:",
        "none_remaining": "Has aprobado todas las habilidades. ¡Buen trabajo!",
        "step_header": "Paso {n}/{total}: {title}",
        "step_safety_en_hint": "⚠ Crítica para la seguridad. En inglés: {en}",
        "step_next_hint": "Responde cualquier cosa para continuar.",
        "step_next_button": "Siguiente",
        "quiz_header": "Pregunta {n}/{total}: {prompt}",
        "quiz_opt": "{num}. {text}",
        "quiz_prompt": "Responde 1, 2 o 3.",
        "quiz_prompt_invalid": "Por favor responde 1, 2 o 3.",
        "quiz_correct": "¡Correcto! ✓",
        "quiz_wrong": "No del todo. La respuesta es: {num}",
        "video_request": "Último paso: envía un video de práctica, menos de 45 segundos.",
        "checking_video": "Revisando tu video…",
        "still_checking": "Aún revisando…",
        "result_pass": "¡Bien hecho! Enviado a tu enfermera para la firma.",
        "result_missed": "Faltó: {desc} en {t}.",
        "result_retry": "Inténtalo de nuevo. {msg}",
        "result_retake": "Repítelo desde el principio. {msg}",
        "result_error": "Algo salió mal al revisar tu video. Inténtalo de nuevo.",
    },
    "tl": {
        "welcome": "Kumusta {first_name}! Ako ang iyong training coach. Mag-reply ng numero ng kasanayang gustong isanay:",
        "menu_header": "Mga kasanayan para sanayin:",
        "menu_item": "{n}. {title}",
        "menu_prompt": "Mag-reply ng numero para magsimula.",
        "unknown_menu": "Hindi ko naintindihan. Mag-reply ng numero ng kasanayan:",
        "none_remaining": "Napasa mo na lahat ng kasanayan — magaling!",
        "step_header": "Hakbang {n}/{total}: {title}",
        "step_safety_en_hint": "⚠ Kritikal sa kaligtasan. Sa Ingles: {en}",
        "step_next_hint": "Mag-reply ng kahit ano para magpatuloy.",
        "step_next_button": "Susunod",
        "quiz_header": "Tanong {n}/{total}: {prompt}",
        "quiz_opt": "{num}. {text}",
        "quiz_prompt": "Mag-reply ng 1, 2, o 3.",
        "quiz_prompt_invalid": "Mangyaring sumagot ng 1, 2, o 3.",
        "quiz_correct": "Tama ✓",
        "quiz_wrong": "Hindi tama. Ang sagot ay: {num}",
        "video_request": "Huling hakbang: magpadala ng practice video, mas mababa sa 45 segundo.",
        "checking_video": "Sinusuri ang video mo…",
        "still_checking": "Sinusuri pa rin…",
        "result_pass": "Magaling — ipinadala sa iyong nurse para sa sign-off.",
        "result_missed": "Nakalimutan: {desc} sa {t}.",
        "result_retry": "Subukan muli. {msg}",
        "result_retake": "Simulan muli mula sa umpisa. {msg}",
        "result_error": "May nangyaring mali sa pagsuri ng iyong video. Subukan muli.",
    },
}


def _t(lang: str, key: str, **kw: Any) -> str:
    tbl = _PROMPT_TEMPLATES.get(lang) or _PROMPT_TEMPLATES["en"]
    return tbl.get(key, _PROMPT_TEMPLATES["en"][key]).format(**kw)


def _fmt_time(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    s = max(0.0, float(seconds))
    m = int(s // 60)
    r = s - m * 60
    return f"{m}:{r:04.1f}"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- conversation accessors ----------
async def _get_or_create_conversation(caregiver_id: str) -> dict:
    db = get_db()
    doc = await db.conversations.find_one({"caregiver_id": caregiver_id})
    if doc:
        return doc
    import uuid as _uuid
    doc = {
        "_id": _uuid.uuid4().hex,
        "caregiver_id": caregiver_id,
        "channel": "web",
        "state": "idle",
        "skill_id": None,
        "step_index": 0,
        "quiz_index": 0,
        "correct_count": 0,
        "pending_attempt_id": None,
        "greeted": False,
        "updated_at": _utcnow(),
    }
    await db.conversations.insert_one(doc)
    return doc


async def _update_conversation(conv_id: str, patch: dict) -> None:
    patch = {**patch, "updated_at": _utcnow()}
    await get_db().conversations.update_one({"_id": conv_id}, {"$set": patch})


async def _log_inbound(caregiver_id: str, text: str, media_id: str | None) -> None:
    import uuid as _uuid
    doc = {
        "_id": _uuid.uuid4().hex,
        "caregiver_id": caregiver_id,
        "direction": "in",
        "channel": "web",
        "text": text or "",
        "media_id": media_id,
        "created_at": _utcnow(),
    }
    await get_db().messages.insert_one(doc)


# ---------- skill / caregiver helpers ----------
async def _get_caregiver(caregiver_id: str) -> dict | None:
    return await get_db().caregivers.find_one({"_id": caregiver_id})


async def _skill(skill_id: str) -> dict | None:
    return await get_db().skills.find_one({"_id": skill_id})


async def _remaining_skills_for(caregiver: dict) -> list[dict]:
    cleared = set(caregiver.get("cleared_skills") or [])
    rows = await get_db().skills.find({}).to_list(length=200)
    out = [s for s in rows if s["_id"] not in cleared]
    out.sort(key=lambda s: s.get("title") or "")
    return out


def _localized_title(skill: dict, lang: str) -> str:
    if lang in ("es", "tl"):
        t = (skill.get("translations") or {}).get(lang) or {}
        if t.get("title"):
            return t["title"]
    return skill.get("title") or ""


def _localized_step(skill: dict, step: dict, lang: str) -> tuple[str, str]:
    """Return (title, instruction) for the step in the caregiver's language,
    falling back to English when the translation is missing."""
    if lang in ("es", "tl"):
        t = (skill.get("translations") or {}).get(lang) or {}
        tsteps = t.get("steps") or []
        match = next((s for s in tsteps if s.get("n") == step.get("n")), None)
        if match:
            return (match.get("title") or step.get("title") or "",
                    match.get("instruction") or step.get("instruction") or "")
    return step.get("title") or "", step.get("instruction") or ""


def _localized_check(skill: dict, check: dict, lang: str) -> tuple[str, str | None]:
    """Return (translated_desc, english_desc_if_safety_critical_else_None)."""
    en = check.get("description") or ""
    translated = en
    if lang in ("es", "tl"):
        t = (skill.get("translations") or {}).get(lang) or {}
        tchecks = t.get("checks") or []
        match = next((c for c in tchecks if c.get("id") == check.get("id")), None)
        if match and match.get("description"):
            translated = match["description"]
    return translated, (en if check.get("safety_critical") else None)


def _localized_quiz(skill: dict, q: dict, lang: str) -> dict:
    out = {"prompt": q.get("prompt") or "", "choices": list(q.get("choices") or [])}
    if lang in ("es", "tl"):
        t = (skill.get("translations") or {}).get(lang) or {}
        tquiz = t.get("quiz") or []
        match = next((x for x in tquiz if x.get("id") == q.get("id")), None)
        if match:
            out["prompt"] = match.get("prompt") or out["prompt"]
            if match.get("choices") and len(match["choices"]) == 3:
                out["choices"] = [str(x) for x in match["choices"]]
    return out


# ---------- outbound helpers ----------
async def _send(
    caregiver_id: str,
    text: str,
    *,
    media_id: str | None = None,
    question_type: str | None = None,
    question_payload: dict | None = None,
) -> None:
    """Thin wrapper around `send_message_async` that forwards question
    metadata so the caregiver UI's quick-reply bar can read directly from
    the latest message's `question_type` + `question_payload`."""
    await send_message_async(
        caregiver_id,
        text,
        media_id=media_id,
        question_type=question_type,
        question_payload=question_payload,
    )


# ---------- menu ----------
async def _send_menu(caregiver_id: str, caregiver: dict, *, prefix: str | None = None) -> None:
    lang = caregiver.get("language") or "en"
    remaining = await _remaining_skills_for(caregiver)
    if not remaining:
        await _send(caregiver_id, _t(lang, "none_remaining"))
        return
    lines = [prefix] if prefix else []
    lines.append(_t(lang, "menu_header"))
    for i, s in enumerate(remaining, start=1):
        lines.append(_t(lang, "menu_item", n=i, title=_localized_title(s, lang)))
    lines.append(_t(lang, "menu_prompt"))
    payload = {
        "skills": [
            {"n": i, "id": s["_id"], "title": _localized_title(s, lang)}
            for i, s in enumerate(remaining, start=1)
        ],
    }
    await _send(
        caregiver_id,
        "\n".join(lines),
        question_type="skill_menu",
        question_payload=payload,
    )


async def _send_step(caregiver_id: str, caregiver: dict, skill: dict, step_index: int) -> None:
    lang = caregiver.get("language") or "en"
    steps = skill.get("steps") or []
    total = len(steps)
    step = steps[step_index]
    title, instruction = _localized_step(skill, step, lang)
    lines = [_t(lang, "step_header", n=step_index + 1, total=total, title=title)]
    if instruction:
        lines.append(instruction)
    # Mention any safety-critical checks that key off this step: we attach
    # all safety-critical checks' English next to the step so caregivers get
    # the explicit English version regardless of translation state.
    sc_checks = [c for c in (skill.get("checks") or []) if c.get("safety_critical")]
    for c in sc_checks:
        translated, en = _localized_check(skill, c, lang)
        if en and translated != en:
            # Only hint once per step (last step).
            if step_index == total - 1:
                lines.append(_t(lang, "step_safety_en_hint", en=f"{en} ({translated})"))
                break
    lines.append(_t(lang, "step_next_hint"))
    payload = {"next_label": _t(lang, "step_next_button")}
    await _send(
        caregiver_id,
        "\n".join(lines),
        media_id=step.get("frame_id"),
        question_type="step",
        question_payload=payload,
    )


async def _send_quiz(caregiver_id: str, caregiver: dict, skill: dict, qi: int) -> None:
    lang = caregiver.get("language") or "en"
    quiz = skill.get("quiz") or []
    q = quiz[qi]
    loc = _localized_quiz(skill, q, lang)
    choices = loc["choices"][:3]
    lines = [_t(lang, "quiz_header", n=qi + 1, total=len(quiz), prompt=loc["prompt"])]
    for i, opt in enumerate(choices):
        lines.append(_t(lang, "quiz_opt", num=i + 1, text=opt))
    lines.append(_t(lang, "quiz_prompt"))
    payload = {
        "options": [
            {"n": i + 1, "text": opt} for i, opt in enumerate(choices)
        ],
    }
    await _send(
        caregiver_id,
        "\n".join(lines),
        question_type="quiz",
        question_payload=payload,
    )


async def _ask_for_video(caregiver_id: str, caregiver: dict) -> None:
    lang = caregiver.get("language") or "en"
    await _send(caregiver_id, _t(lang, "video_request"))


# ---------- menu-reply parsing ----------
_NUMBER_RE = re.compile(r"\b(\d{1,2})\b")
_LETTER_RE = re.compile(r"\b([a-cA-C])\b")


def _parse_number(text: str) -> int | None:
    m = _NUMBER_RE.search(text or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _parse_quiz_answer(text: str) -> int | None:
    """Return the 1-based option number for a quiz reply.

    Accepts both ``1/2/3`` and ``A/B/C`` (case-insensitive). Any other
    input returns None so the caller can send the localized retry
    prompt ("Please answer 1, 2, or 3.").
    """
    n = _parse_number(text or "")
    if n is not None and 1 <= n <= 3:
        return n
    m = _LETTER_RE.search(text or "")
    if m:
        return ord(m.group(1).lower()) - ord("a") + 1
    return None


# ---------- the FSM ----------
async def handle_inbound(
    caregiver_id: str,
    text: str | None,
    media_id: str | None,
    channel: str = "web",
) -> dict:
    """Advance the conversation. Returns the new conversation state (public shape)."""
    text = (text or "").strip()
    caregiver = await _get_caregiver(caregiver_id)
    if not caregiver:
        return {"error": "caregiver_not_found"}
    lang = caregiver.get("language") or "en"

    # Log the inbound before anything else.
    await _log_inbound(caregiver_id, text, media_id)

    conv = await _get_or_create_conversation(caregiver_id)
    state = conv.get("state") or "idle"

    # First contact ever: send a welcome before falling through.
    if not conv.get("greeted"):
        first_name = (caregiver.get("name") or "").split(" ")[0] or "there"
        await _send(caregiver_id, _t(lang, "welcome", first_name=first_name))
        await _update_conversation(conv["_id"], {"greeted": True})
        await _send_menu(caregiver_id, caregiver)
        # Return — the caregiver will reply with a number next.
        return await _public_state(caregiver_id)

    # ---- state: idle ----
    if state == "idle":
        remaining = await _remaining_skills_for(caregiver)
        n = _parse_number(text)
        if n and 1 <= n <= len(remaining):
            chosen = remaining[n - 1]
            await _update_conversation(conv["_id"], {
                "state": "in_lesson",
                "skill_id": chosen["_id"],
                "step_index": 0,
                "quiz_index": 0,
                "correct_count": 0,
            })
            if (chosen.get("steps") or []):
                await _send_step(caregiver_id, caregiver, chosen, 0)
            else:
                await _advance_from_lesson(caregiver_id, caregiver, chosen, conv["_id"], last_step=True)
            return await _public_state(caregiver_id)
        # Not a menu reply: forward to answer_question.
        if text:
            await _run_answer_question(caregiver_id, text, lang)
        else:
            await _send_menu(caregiver_id, caregiver, prefix=_t(lang, "unknown_menu"))
        return await _public_state(caregiver_id)

    # ---- state: in_lesson ----
    if state == "in_lesson":
        skill = await _skill(conv.get("skill_id") or "")
        if not skill:
            await _update_conversation(conv["_id"], {"state": "idle", "skill_id": None})
            await _send_menu(caregiver_id, caregiver)
            return await _public_state(caregiver_id)
        steps = skill.get("steps") or []
        step_index = int(conv.get("step_index") or 0) + 1
        if step_index < len(steps):
            await _update_conversation(conv["_id"], {"step_index": step_index})
            await _send_step(caregiver_id, caregiver, skill, step_index)
            return await _public_state(caregiver_id)
        # Done with steps → quiz or video.
        await _advance_from_lesson(caregiver_id, caregiver, skill, conv["_id"], last_step=True)
        return await _public_state(caregiver_id)

    # ---- state: quiz ----
    if state == "quiz":
        skill = await _skill(conv.get("skill_id") or "")
        quiz = (skill or {}).get("quiz") or []
        qi = int(conv.get("quiz_index") or 0)
        q = quiz[qi] if qi < len(quiz) else None
        if not q:
            await _update_conversation(conv["_id"], {"state": "awaiting_video"})
            await _ask_for_video(caregiver_id, caregiver)
            return await _public_state(caregiver_id)
        chosen = _parse_quiz_answer(text)
        if not chosen or chosen < 1 or chosen > 3:
            # Resend the current quiz question with the full payload so
            # the quick-reply bar still has an active `question_type:
            # "quiz"` message to key off.
            await _send(caregiver_id, _t(lang, "quiz_prompt_invalid"))
            await _send_quiz(caregiver_id, caregiver, skill, qi)
            return await _public_state(caregiver_id)
        correct_idx = int(q.get("answer_index") or 0)
        correct = (chosen - 1) == correct_idx
        if correct:
            await _send(caregiver_id, _t(lang, "quiz_correct"))
        else:
            await _send(caregiver_id, _t(lang, "quiz_wrong", num=correct_idx + 1))
        patch: dict = {"quiz_index": qi + 1}
        if correct:
            patch["correct_count"] = int(conv.get("correct_count") or 0) + 1
        await _update_conversation(conv["_id"], patch)
        if qi + 1 < len(quiz):
            await _send_quiz(caregiver_id, caregiver, skill, qi + 1)
        else:
            await _update_conversation(conv["_id"], {"state": "awaiting_video"})
            await _ask_for_video(caregiver_id, caregiver)
        return await _public_state(caregiver_id)

    # ---- state: awaiting_video ----
    if state == "awaiting_video":
        if not media_id:
            # Treat as free text — route via answer_question so the caregiver
            # isn't stuck. Keep state unchanged so they can still send the video.
            if text:
                await _run_answer_question(caregiver_id, text, lang)
            else:
                await _ask_for_video(caregiver_id, caregiver)
            return await _public_state(caregiver_id)
        # Video received. Create an attempt and watch the grading result.
        skill_id = conv.get("skill_id")
        if not skill_id:
            await _update_conversation(conv["_id"], {"state": "idle"})
            await _send_menu(caregiver_id, caregiver)
            return await _public_state(caregiver_id)
        try:
            attempt_id = await _start_grading_from_media(skill_id, caregiver_id, media_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("failed to start grading: %s", exc)
            await _send(caregiver_id, _t(lang, "result_error"))
            await _update_conversation(conv["_id"], {"state": "awaiting_video"})
            return await _public_state(caregiver_id)
        await _update_conversation(conv["_id"], {
            "state": "awaiting_result",
            "pending_attempt_id": attempt_id,
        })
        await _send(caregiver_id, _t(lang, "checking_video"))
        # Spawn a watcher that polls the attempt and reports the result.
        asyncio.get_running_loop().create_task(
            _watch_attempt(caregiver_id, attempt_id, skill_id)
        )
        return await _public_state(caregiver_id)

    # ---- state: awaiting_result ----
    if state == "awaiting_result":
        if text:
            await _send(caregiver_id, _t(lang, "still_checking"))
        return await _public_state(caregiver_id)

    # Fallback.
    await _update_conversation(conv["_id"], {"state": "idle"})
    await _send_menu(caregiver_id, caregiver)
    return await _public_state(caregiver_id)


async def _advance_from_lesson(
    caregiver_id: str,
    caregiver: dict,
    skill: dict,
    conv_id: str,
    *,
    last_step: bool,
) -> None:
    """After the last step: start the quiz if there is one, else ask for the video."""
    quiz = skill.get("quiz") or []
    if quiz:
        await _update_conversation(conv_id, {"state": "quiz", "quiz_index": 0})
        await _send_quiz(caregiver_id, caregiver, skill, 0)
    else:
        await _update_conversation(conv_id, {"state": "awaiting_video"})
        await _ask_for_video(caregiver_id, caregiver)


# ---------- lessons-tab shortcut ----------
async def open_lesson(caregiver_id: str, skill_id: str) -> dict:
    """Jump directly to a lesson from outside the chat (e.g. the Lessons tab).

    Mirrors "picked the skill from the menu by its number" without the
    caregiver having to type anything. Transitions the conversation to
    `in_lesson` and sends step 0 of the chosen skill. Returns the public
    conversation state so the caller can navigate confidently.

    Idempotent: calling with the same skill again while the caregiver is
    already in that lesson restarts it from step 0.
    """
    caregiver = await _get_caregiver(caregiver_id)
    if not caregiver:
        return {"error": "caregiver_not_found"}
    skill = await _skill(skill_id)
    if not skill:
        return {"error": "skill_not_found"}
    conv = await _get_or_create_conversation(caregiver_id)
    await _update_conversation(conv["_id"], {
        "state": "in_lesson",
        "skill_id": skill_id,
        "step_index": 0,
        "quiz_index": 0,
        "correct_count": 0,
        "greeted": True,
    })
    steps = skill.get("steps") or []
    if steps:
        await _send_step(caregiver_id, caregiver, skill, 0)
    else:
        await _advance_from_lesson(caregiver_id, caregiver, skill, conv["_id"], last_step=True)
    return await _public_state(caregiver_id)


# ---------- grading hand-off ----------
async def _start_grading_from_media(skill_id: str, caregiver_id: str, media_id: str) -> str:
    """Load the uploaded bytes from GridFS, call the real grading ingest, enqueue grading."""
    from features.grading.background import enqueue_grade
    from features.grading.ingest import ingest_clip
    from fastapi import UploadFile
    import io
    import tempfile
    from media.store import get_media_store

    store = get_media_store()
    stream, content_type, filename = await store.get(media_id)
    # Drain to bytes.
    buf = bytearray()
    async for chunk in stream:
        buf.extend(chunk)
    bio = io.BytesIO(bytes(buf))
    bio.seek(0)
    # FastAPI's UploadFile wraps a SpooledTemporaryFile; a BytesIO works for .read().
    upload = UploadFile(filename=filename or "clip.mp4", file=bio)

    result = await ingest_clip(file=upload, skill_id=skill_id, caregiver_id=caregiver_id)
    enqueue_grade(result["attempt_id"], skill_id, caregiver_id, result["clip_id"])
    return result["attempt_id"]


async def _watch_attempt(caregiver_id: str, attempt_id: str, skill_id: str) -> None:
    """Poll the attempt until it reaches a terminal grading state and send the result."""
    import asyncio as _asyncio

    db = get_db()
    # 150 polls × 2 s = 5 min safety ceiling. Phase-3's own stale sweeper handles 10 min.
    for _ in range(150):
        await _asyncio.sleep(2)
        a = await db.attempts.find_one({"_id": attempt_id})
        if not a:
            return
        status = a.get("status")
        if status == "grading":
            continue
        # Terminal.
        caregiver = await _get_caregiver(caregiver_id)
        if not caregiver:
            return
        lang = caregiver.get("language") or "en"
        skill = await _skill(skill_id)
        msg_for_caregiver = (a.get("message_for_caregiver") or "").strip()
        if status == "ready_to_sign":
            # First missed check (if any) with its timestamp.
            missed = _first_missed(a, skill, lang)
            if missed:
                desc, t = missed
                await _send(caregiver_id, _t(lang, "result_missed", desc=desc, t=t))
            await _send(caregiver_id, _t(lang, "result_pass"))
        elif status == "needs_practice":
            missed = _first_missed(a, skill, lang)
            if missed:
                desc, t = missed
                await _send(caregiver_id, _t(lang, "result_missed", desc=desc, t=t))
            await _send(caregiver_id, _t(lang, "result_retry", msg=msg_for_caregiver))
        elif status == "retake_required":
            await _send(caregiver_id, _t(lang, "result_retake", msg=msg_for_caregiver))
        else:  # grading_error
            await _send(caregiver_id, _t(lang, "result_error"))
        # Back to idle so the menu can re-appear.
        conv = await db.conversations.find_one({"caregiver_id": caregiver_id})
        if conv:
            await _update_conversation(conv["_id"], {
                "state": "idle",
                "skill_id": None,
                "step_index": 0,
                "quiz_index": 0,
                "correct_count": 0,
                "pending_attempt_id": None,
            })
        return
    logger.warning("watcher gave up on attempt %s", attempt_id)


def _first_missed(attempt: dict, skill: dict | None, lang: str) -> tuple[str, str] | None:
    """Return (description-in-lang, m:ss.s) for the first failed check, else None."""
    for c in attempt.get("checks") or []:
        if c.get("result") == "fail":
            desc = c.get("description") or ""
            if skill:
                skill_check = next(
                    (sc for sc in (skill.get("checks") or []) if sc.get("id") == c.get("id")),
                    None,
                )
                if skill_check:
                    translated, _en = _localized_check(skill, skill_check, lang)
                    if translated:
                        desc = translated
            return desc, _fmt_time(c.get("time"))
    return None


# ---------- answer_question handoff ----------
async def _run_answer_question(caregiver_id: str, text: str, lang: str) -> None:
    """Call the questions pipeline in-process; it will log the outbound reply itself."""
    try:
        from features.questions.pipeline import answer_question_async
        await answer_question_async(caregiver_id, text, lang)
    except Exception as exc:  # noqa: BLE001
        logger.exception("answer_question failed: %s", exc)
        await _send(caregiver_id, _t(lang, "result_error"))


# ---------- public state projector ----------
async def _public_state(caregiver_id: str) -> dict:
    conv = await get_db().conversations.find_one({"caregiver_id": caregiver_id})
    if not conv:
        return {"state": "idle"}
    return {
        "id": conv["_id"],
        "state": conv.get("state"),
        "skill_id": conv.get("skill_id"),
        "step_index": conv.get("step_index") or 0,
        "quiz_index": conv.get("quiz_index") or 0,
        "correct_count": conv.get("correct_count") or 0,
        "pending_attempt_id": conv.get("pending_attempt_id"),
        "greeted": bool(conv.get("greeted")),
        "updated_at": conv.get("updated_at"),
    }
