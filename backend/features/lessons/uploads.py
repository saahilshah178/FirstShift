"""Chunked upload endpoints for the lessons feature.

- `POST /uploads`                          — init a chunked upload.
- `PUT /uploads/{upload_id}/chunks/{idx}`  — raw-bytes chunk.
- `POST /uploads/{upload_id}/complete`     — assemble, probe, create a job.

Temp staging dir: `/tmp/lessons/<upload_id>/`. Assembled file is handed
off to the pipeline runner; the staging dir is deleted after assembly.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from db import get_db

from .runner import kick_job
from .transcode import ffprobe
from .pipeline import utcnow_iso

logger = logging.getLogger("firstshift.lessons.uploads")

MAX_UPLOAD_BYTES = 300 * 1024 * 1024  # 300 MB
CHUNK_SIZE = 8 * 1024 * 1024          # 8 MB
STAGING_ROOT = Path(tempfile.gettempdir()) / "lessons"
ACCEPTED_INIT_TYPES = {"video/mp4", "video/quicktime", "video/webm"}

router = APIRouter()


def _staging_dir(upload_id: str) -> Path:
    return STAGING_ROOT / upload_id


@router.post("/uploads")
async def init_upload(body: dict) -> dict:
    """Open a chunked upload.

    Body: `{filename, size, content_type}`.
    - 413 if `size` > 300 MB.
    - 415 if content_type not in the mp4/mov/webm allowlist.
    """
    filename = (body.get("filename") or "upload.bin").strip()
    try:
        size = int(body.get("size") or 0)
    except (ValueError, TypeError):
        size = 0
    content_type = (body.get("content_type") or "").strip().lower()

    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_BYTES} bytes.")
    if content_type not in ACCEPTED_INIT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported content-type: {content_type!r}")

    upload_id = uuid.uuid4().hex
    sd = _staging_dir(upload_id)
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "_meta.txt").write_text(f"{filename}\n{size}\n{content_type}\n", encoding="utf-8")
    return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE}


@router.put("/uploads/{upload_id}/chunks/{index}")
async def put_chunk(upload_id: str, index: int, request: Request) -> dict:
    sd = _staging_dir(upload_id)
    if not sd.exists():
        raise HTTPException(status_code=404, detail="upload not found")
    data = await request.body()
    # Guard against runaway: enforce per-chunk size.
    if len(data) > CHUNK_SIZE + 1024:  # small slack
        raise HTTPException(status_code=413, detail="chunk larger than CHUNK_SIZE")
    out = sd / f"part-{index:06d}"
    out.write_bytes(data)
    return {"ok": True, "bytes": len(data)}


@router.post("/uploads/{upload_id}/complete")
async def complete_upload(upload_id: str, body: dict | None = None) -> dict:
    """Assemble chunks, probe the real file, create a `lesson_jobs` row and kick the pipeline."""
    sd = _staging_dir(upload_id)
    if not sd.exists():
        raise HTTPException(status_code=404, detail="upload not found")

    source_credit = ((body or {}).get("source_credit") or "").strip()
    parts = sorted([p for p in sd.iterdir() if p.name.startswith("part-")])
    if not parts:
        raise HTTPException(status_code=422, detail="no chunks received")

    assembled = sd / "assembled.bin"
    with open(assembled, "wb") as out_f:
        for part in parts:
            with open(part, "rb") as f:
                shutil.copyfileobj(f, out_f, length=1024 * 1024)

    total_bytes = assembled.stat().st_size
    if total_bytes > MAX_UPLOAD_BYTES:
        shutil.rmtree(sd, ignore_errors=True)
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_BYTES} bytes.")

    # Probe the real file (not the client-supplied content-type).
    try:
        probe = await ffprobe(str(assembled))
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(sd, ignore_errors=True)
        raise HTTPException(status_code=415, detail=f"Not a readable video: {exc}") from exc
    if not probe.has_video_stream:
        shutil.rmtree(sd, ignore_errors=True)
        raise HTTPException(status_code=415, detail="File has no video stream.")
    if probe.duration_s > 120.0:
        shutil.rmtree(sd, ignore_errors=True)
        raise HTTPException(status_code=422, detail="Video is longer than 2 minutes")

    # Hand-off: move the assembled file to a stable path the runner can read.
    stable_path = STAGING_ROOT / f"{upload_id}-assembled.mp4"
    try:
        shutil.move(str(assembled), str(stable_path))
    except Exception:  # noqa: BLE001
        # Fallback: copy then unlink.
        shutil.copyfile(str(assembled), str(stable_path))
        try:
            assembled.unlink()
        except Exception:  # noqa: BLE001
            pass
    shutil.rmtree(sd, ignore_errors=True)

    job_id = uuid.uuid4().hex
    db = get_db()
    doc = {
        "_id": job_id,
        "status": "converting",
        "error": "",
        "video_id": None,
        "source_credit": source_credit,
        "skill_id": None,
        "duration_s": probe.duration_s,
        "draft": {"title": "", "steps": [], "checks": [], "quiz": []},
        "problems": [],
        "draft_rev": 0,
        "heartbeat_at": utcnow_iso(),
        "created_at": utcnow_iso(),
        "updated_at": utcnow_iso(),
    }
    await db.lesson_jobs.insert_one(doc)

    kick_job(job_id, assembled_path=str(stable_path))
    return {"job_id": job_id}
