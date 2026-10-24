"""HTTP routes for the caregiver chat channel.

Mounted at `/api/channel`. The `GET /` placeholder is preserved so the
Phase-1 auto-discovery smoke-test keeps passing.
"""
from __future__ import annotations

import io
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from db import get_db
from media.store import get_media_store

from .state_machine import handle_inbound, _public_state  # noqa: F401

logger = logging.getLogger("firstshift.channel.routes")

router = APIRouter()


ACCEPTED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}


@router.get("/messages/{caregiver_id}")
async def list_messages(caregiver_id: str) -> dict:
    db = get_db()
    rows = await db.messages.find({"caregiver_id": caregiver_id}).sort("created_at", 1).to_list(length=500)
    out = [
        {
            "id": r["_id"],
            "direction": r.get("direction"),
            "channel": r.get("channel"),
            "text": r.get("text") or "",
            "media_id": r.get("media_id"),
            "created_at": r.get("created_at"),
        }
        for r in rows
    ]
    return {"messages": out}


@router.get("/conversation/{caregiver_id}")
async def get_conversation(caregiver_id: str) -> dict:
    db = get_db()
    conv = await db.conversations.find_one({"caregiver_id": caregiver_id})
    if not conv:
        return {"state": "idle", "greeted": False}
    return {
        "id": str(conv["_id"]),
        "state": conv.get("state"),
        "skill_id": conv.get("skill_id"),
        "step_index": conv.get("step_index") or 0,
        "quiz_index": conv.get("quiz_index") or 0,
        "correct_count": conv.get("correct_count") or 0,
        "pending_attempt_id": conv.get("pending_attempt_id"),
        "greeted": bool(conv.get("greeted")),
        "updated_at": conv.get("updated_at"),
    }


@router.post("/inbound")
async def inbound(body: dict) -> dict:
    caregiver_id = str(body.get("caregiver_id") or "").strip()
    if not caregiver_id:
        raise HTTPException(status_code=422, detail="caregiver_id required")
    text = body.get("text")
    media_id = body.get("media_id")
    result = await handle_inbound(
        caregiver_id=caregiver_id,
        text=text if isinstance(text, str) else None,
        media_id=media_id if isinstance(media_id, str) and media_id else None,
    )
    return {"ok": True, "conversation": result}


@router.post("/inbound-video")
async def inbound_video(
    caregiver_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    """Convenience endpoint: stores the raw video in MediaStore (so the inbound
    message has a media_id to render), then runs the FSM with media_id set.

    The FSM's `awaiting_video` branch will transcode via grading.ingest_clip and
    enqueue grading. Returns `{ok, conversation, media_id, attempt_id}`."""
    content_type = (file.content_type or "").lower()
    if content_type not in ACCEPTED_VIDEO_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported content-type: {content_type!r}")
    buf = bytearray()
    chunk_size = 1024 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="file exceeds 100 MB")

    data = bytes(buf)
    store = get_media_store()
    media_id = await store.save(data, content_type, filename=file.filename or "clip.webm")

    result = await handle_inbound(
        caregiver_id=caregiver_id.strip(),
        text=None,
        media_id=media_id,
    )
    return {"ok": True, "media_id": media_id, "conversation": result}
