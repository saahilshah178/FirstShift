"""Questions pipeline: AI-first answer with policy + card context.

- Prepends existing `cards` (fast lane for FAQ repeats) and all `policies`
  (slow lane for governance) into the Gemini context.
- Response schema: `{covered: bool, answer: str, source_title: str}`.
- Covered → reply in caregiver's language, log the question as `answered`
  with `source="ai"` (or `source="card"` if the source_title matches an
  existing card verbatim).
- Not covered → reply "I've asked your care manager" (in language) and
  log the question with `status="waiting_owner"`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from db import get_db

from ai.gemini import call_gemini
from services.channel_service import send_message_async

logger = logging.getLogger("firstshift.questions.pipeline")


_WAITING_OWNER_FALLBACK = {
    "en": "I've asked your care manager and will send their answer here when it's ready.",
    "es": "Le pregunté a tu administradora de cuidados y te enviaré su respuesta aquí cuando esté lista.",
    "tl": "Tinanong ko ang iyong care manager at ipapadala ko dito ang kanyang sagot kapag handa na.",
}

# Copy pass (Batch-4 #22/#23): Spanish must use `tú` throughout and
# refer to the role in the singular ("administradora de cuidados").
# `_WAITING_OWNER_FALLBACK["es"]` above already does; keep this list
# as the authoritative source whenever we add new fallbacks.

_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "covered": {"type": "boolean"},
        "answer": {"type": "string"},
        "source_title": {"type": "string"},
    },
    "required": ["covered", "answer", "source_title"],
}

_SYSTEM = (
    "You are a home-care agency's training assistant. The caregiver asked a question. "
    "Decide whether their question is already covered by one of the agency's internal "
    "cards or policies below. If it is, answer in {language_name} using only what the "
    "card or policy says, and set source_title to the matching card question (prefix "
    "'Card: ') or policy title (prefix 'Policy: '). Keep the answer under 80 words. "
    "If nothing covers it, set covered=false, answer='' and source_title=''. Never "
    "invent policy that isn't in the list."
)

_LANG_NAMES = {"en": "English", "es": "Spanish", "tl": "Tagalog"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _gather_context() -> tuple[list[dict], list[dict]]:
    db = get_db()
    cards = await db.cards.find({}).sort("created_at", -1).to_list(length=200)
    policies = await db.policies.find({}).to_list(length=100)
    return cards, policies


def _build_prompt(language: str, cards: list[dict], policies: list[dict], question: str) -> str:
    lang_name = _LANG_NAMES.get(language, "English")
    parts = [_SYSTEM.format(language_name=lang_name)]
    if cards:
        parts.append("\n\nAgency cards (previous answers to similar questions):")
        for c in cards:
            parts.append(f"- Card: {c.get('question','')}\n  → {c.get('answer','')}")
    if policies:
        parts.append("\n\nAgency policies:")
        for p in policies:
            parts.append(f"- Policy: {p.get('title','')}\n  {p.get('text','')}")
    parts.append(f"\n\nCaregiver question: {question}")
    parts.append("\n\nReturn JSON per the schema.")
    return "\n".join(parts)


async def _log_question(
    *,
    caregiver_id: str,
    text: str,
    language: str,
    status: str,
    answer: str | None,
    card_id: str | None,
    source: str,
) -> str:
    db = get_db()
    qid = uuid.uuid4().hex
    doc = {
        "_id": qid,
        "caregiver_id": caregiver_id,
        "text": text,
        "language": language,
        "status": status,
        "answer": answer,
        "card_id": card_id,
        "source": source,
        "created_at": _utcnow(),
        "answered_at": _utcnow() if status == "answered" else None,
    }
    await db.questions.insert_one(doc)
    return qid


async def _find_card_by_source_title(source_title: str) -> dict | None:
    """When Gemini says 'Card: <question>' we try to resolve to an actual card row."""
    if not source_title or not source_title.lower().startswith("card:"):
        return None
    needle = source_title.split(":", 1)[1].strip()
    db = get_db()
    # Exact match on card.question first; fall back to case-insensitive.
    row = await db.cards.find_one({"question": needle})
    if row:
        return row
    import re
    return await db.cards.find_one({"question": {"$regex": f"^{re.escape(needle)}$", "$options": "i"}})


async def answer_question_async(caregiver_id: str, text: str, language: str | None = None) -> dict:
    """Call Gemini with full context, deliver the caregiver message, and
    persist the question. Returns the public shape used by the sync stub."""
    db = get_db()
    caregiver = await db.caregivers.find_one({"_id": caregiver_id})
    if not caregiver:
        logger.warning("answer_question_async: caregiver %s not found", caregiver_id)
        return {
            "question_id": None,
            "caregiver_id": caregiver_id,
            "question": text,
            "status": "waiting_owner",
            "answer": "",
            "citations": [],
            "confidence": 0.0,
            "answered_at": None,
            "model": "stub",
        }
    lang = language or caregiver.get("language") or "en"

    cards, policies = await _gather_context()
    prompt = _build_prompt(lang, cards, policies, text)

    try:
        result = await call_gemini(prompt=prompt, media_uuids=[], response_schema=_ANSWER_SCHEMA)
    except Exception as exc:  # noqa: BLE001
        logger.exception("call_gemini for answer_question failed: %s", exc)
        result = {"covered": False, "answer": "", "source_title": ""}

    covered = bool(result.get("covered"))
    answer_text = (result.get("answer") or "").strip()
    source_title = (result.get("source_title") or "").strip()

    if covered and answer_text:
        card_row = await _find_card_by_source_title(source_title)
        card_id = card_row["_id"] if card_row else None
        source = "card" if card_row else "ai"
        source_label = source_title or "agency guidance"
        delivered_text = f"{answer_text}\n\n({source_label})"
        await send_message_async(caregiver_id, delivered_text)
        qid = await _log_question(
            caregiver_id=caregiver_id,
            text=text,
            language=lang,
            status="answered",
            answer=answer_text,
            card_id=card_id,
            source=source,
        )
        answered_at = _utcnow()
        return {
            "question_id": qid,
            "caregiver_id": caregiver_id,
            "question": text,
            "status": "answered",
            "answer": answer_text,
            "citations": [{"source_title": source_title}],
            "confidence": 1.0 if card_row else 0.75,
            "answered_at": answered_at,
            "model": "gemini",
        }

    # Not covered — escalate.
    fallback = _WAITING_OWNER_FALLBACK.get(lang) or _WAITING_OWNER_FALLBACK["en"]
    await send_message_async(caregiver_id, fallback)
    qid = await _log_question(
        caregiver_id=caregiver_id,
        text=text,
        language=lang,
        status="waiting_owner",
        answer=None,
        card_id=None,
        source="owner",
    )
    return {
        "question_id": qid,
        "caregiver_id": caregiver_id,
        "question": text,
        "status": "waiting_owner",
        "answer": "",
        "citations": [],
        "confidence": 0.0,
        "answered_at": None,
        "model": "gemini",
    }


async def deliver_owner_answer(question_id: str, answer_text: str) -> dict:
    """Care manager typed/transcribed an answer. Create a card, mark the
    question answered, send to the caregiver."""
    db = get_db()
    question = await db.questions.find_one({"_id": question_id})
    if not question:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="question not found")
    if question.get("status") == "answered":
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="question already answered")

    answer_text = (answer_text or "").strip()
    if not answer_text:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="answer text required")

    card_id = uuid.uuid4().hex
    card_doc = {
        "_id": card_id,
        "role": "caregiver",
        "question": question.get("text") or "",
        "answer": answer_text,
        "created_at": _utcnow(),
    }
    await db.cards.insert_one(card_doc)
    await db.questions.update_one(
        {"_id": question_id},
        {"$set": {
            "status": "answered",
            "answer": answer_text,
            "card_id": card_id,
            "source": "owner",
            "answered_at": _utcnow(),
        }},
    )

    # Deliver to the caregiver in their language. The owner typed in English (or
    # a mix); we translate the delivery message when the caregiver's language is
    # es or tl so DONE WHEN #3 (delivery in-language) holds.
    caregiver = await db.caregivers.find_one({"_id": question["caregiver_id"]})
    lang = (caregiver or {}).get("language") or "en"
    delivered = await _translate_if_needed(answer_text, lang)
    await send_message_async(question["caregiver_id"], delivered)

    return {"question_id": question_id, "card_id": card_id, "delivered_text": delivered}


async def _translate_if_needed(text: str, lang: str) -> str:
    if lang == "en":
        return text
    try:
        schema = {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }
        lang_name = _LANG_NAMES.get(lang, "English")
        prompt = (
            f"Translate the following into {lang_name}. Keep tone professional and "
            f"concise. Return JSON {{text: '...'}}.\n\n{text}"
        )
        res = await call_gemini(prompt=prompt, media_uuids=[], response_schema=schema)
        out = (res.get("text") or "").strip()
        return out or text
    except Exception as exc:  # noqa: BLE001
        logger.exception("translation on delivery failed: %s", exc)
        return text


async def transcribe_audio(media_id: str) -> str:
    """Call Gemini with the stored audio clip; return a transcript string."""
    schema = {
        "type": "object",
        "properties": {"transcript": {"type": "string"}},
        "required": ["transcript"],
    }
    prompt = (
        "Transcribe this audio verbatim. Return JSON {transcript: '...'}. "
        "If there is no speech, return an empty string."
    )
    result = await call_gemini(prompt=prompt, media_uuids=[media_id], response_schema=schema)
    return (result.get("transcript") or "").strip()
