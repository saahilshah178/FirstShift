"""HTTP routes for the questions inbox + voice transcription.

Mounted at `/api/questions`. Keeps the Phase-1 `GET /` + `GET /list` shapes.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from db import get_db
from media.store import get_media_store

from .pipeline import answer_question_async, deliver_owner_answer, transcribe_audio

logger = logging.getLogger("firstshift.questions.routes")

router = APIRouter()


ACCEPTED_AUDIO_TYPES = {"audio/webm", "audio/mpeg", "audio/wav", "audio/aac", "audio/ogg"}


# ---- inbox (agency UI) ----
@router.get("/inbox")
async def inbox() -> dict:
    """Waiting-owner first, then answered — care manager's work queue."""
    db = get_db()
    rows = await db.questions.find({}).sort("created_at", -1).to_list(length=500)
    caregivers = await db.caregivers.find(
        {"_id": {"$in": list({r["caregiver_id"] for r in rows})}},
        {"_id": 1, "name": 1, "language": 1},
    ).to_list(length=200)
    c_by_id = {c["_id"]: c for c in caregivers}

    def _row(r: dict) -> dict:
        c = c_by_id.get(r["caregiver_id"]) or {}
        return {
            "id": r["_id"],
            "caregiver": {
                "id": r["caregiver_id"],
                "name": c.get("name"),
                "language": c.get("language"),
            },
            "text": r.get("text") or "",
            "language": r.get("language") or c.get("language") or "en",
            "status": r.get("status"),
            "answer": r.get("answer"),
            "source": r.get("source"),
            "card_id": r.get("card_id"),
            "created_at": r.get("created_at"),
            "answered_at": r.get("answered_at"),
        }

    waiting = [_row(r) for r in rows if r.get("status") == "waiting_owner"]
    answered = [_row(r) for r in rows if r.get("status") == "answered"]
    return {"waiting": waiting, "answered": answered, "total": len(rows)}


# ---- ask (caregiver-side convenience; the state machine also calls the pipeline) ----
@router.post("/ask")
async def ask(body: dict) -> dict:
    caregiver_id = str(body.get("caregiver_id") or "").strip()
    text = str(body.get("text") or "").strip()
    if not caregiver_id or not text:
        raise HTTPException(status_code=422, detail="caregiver_id and text required")
    result = await answer_question_async(caregiver_id, text)
    return result


# ---- answer (care manager types or submits transcript) ----
@router.post("/{question_id}/answer")
async def answer(question_id: str, body: dict) -> dict:
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="text required")
    return await deliver_owner_answer(question_id, text)


# ---- voice transcribe ----
@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict:
    content_type = (file.content_type or "").lower()
    if content_type not in ACCEPTED_AUDIO_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported audio content-type: {content_type!r}")
    buf = bytearray()
    chunk_size = 512 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="audio exceeds 25 MB")
    store = get_media_store()
    media_id = await store.save(bytes(buf), content_type, filename=file.filename or "voice.webm")
    transcript = await transcribe_audio(media_id)
    return {"media_id": media_id, "transcript": transcript}


# ---- policies list (used by the inbox UI as reference) ----
@router.get("/policies")
async def policies() -> dict:
    db = get_db()
    rows = await db.policies.find({}).to_list(length=100)
    return {
        "policies": [
            {"id": r["_id"], "title": r.get("title"), "text": r.get("text")}
            for r in rows
        ]
    }
