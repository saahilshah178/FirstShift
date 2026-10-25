"""Clip ingest for the grading feature.

Validate uploaded video, encode via the SINGLE media encoder helper,
store the mp4 bytes via `MediaStore`, create an `attempts` row with
status `"grading"`. Encoding config lives in `backend/media/encode.py`
(see Stage 1 — Media pipeline audit in `docs/CHANGELOG.md`).
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile

from db import get_db
from media.encode import EncodeError, encode_mp4
from media.store import get_media_store

logger = logging.getLogger("firstshift.grading.ingest")

MAX_BYTES = 100 * 1024 * 1024
MIN_DURATION = 3.0
MAX_DURATION = 45.0


def _ffprobe_json(path: Path) -> dict:
    """Return the full ffprobe JSON for the file; raise on decode failure."""
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(path),
        ],
        check=False, capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {r.stderr.strip()[:200]}")
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ffprobe produced non-JSON: {exc}") from exc
    if not data.get("streams"):
        raise RuntimeError("no streams decoded")
    return data


def _duration_from_probe(probe: dict) -> float:
    try:
        return float(probe.get("format", {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


async def ingest_clip(
    *, file: UploadFile, skill_id: str, caregiver_id: str,
) -> dict:
    db = get_db()

    skill = await db.skills.find_one({"_id": skill_id}, {"_id": 1})
    if not skill:
        raise HTTPException(status_code=422, detail=f"skill not found: {skill_id}")
    caregiver = await db.caregivers.find_one({"_id": caregiver_id}, {"_id": 1})
    if not caregiver:
        raise HTTPException(status_code=422, detail=f"caregiver not found: {caregiver_id}")

    # Stream to memory with a hard cap.
    buf = bytearray()
    chunk_size = 1024 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > MAX_BYTES:
            raise HTTPException(status_code=413, detail=f"file exceeds {MAX_BYTES} bytes")

    with tempfile.TemporaryDirectory(prefix="fs-ingest-") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / (file.filename or "upload.bin")
        with src.open("wb") as fh:
            fh.write(bytes(buf))

        try:
            probe = _ffprobe_json(src)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=415,
                detail=f"cannot decode video: {exc}",
            ) from exc

        duration = _duration_from_probe(probe)
        if duration < MIN_DURATION or duration > MAX_DURATION:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"clip must be {MIN_DURATION:g}-{MAX_DURATION:g} seconds, "
                    f"got {duration:.2f}s"
                ),
            )

        dst = tmp_path / "out.mp4"
        try:
            await encode_mp4(src, dst, duration_s=duration)
        except EncodeError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc

        mp4_bytes = dst.read_bytes()

    store = get_media_store()
    clip_id = await store.save(
        mp4_bytes, "video/mp4", filename=f"{uuid.uuid4().hex}.mp4"
    )

    attempt_id = uuid.uuid4().hex
    attempt_doc = {
        "_id": attempt_id,
        "caregiver_id": caregiver_id,
        "skill_id": skill_id,
        "clip_id": clip_id,
        "duration": round(duration, 3),
        "checks": [],
        "overall": None,
        "status": "grading",
        "verdict": None,
        "score": None,
        "message_for_caregiver": "",
        "runs_used": 0,
        "graded_once": False,
        "raw_runs": [],
        "frame_ids": [],
        "error": None,
        "reviewed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.attempts.insert_one(attempt_doc)
    logger.info("ingest: attempt=%s clip=%s duration=%.2fs", attempt_id, clip_id, duration)
    return {"attempt_id": attempt_id, "clip_id": clip_id, "status": "grading"}
