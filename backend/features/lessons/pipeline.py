"""Pipeline stages for the lessons feature.

Each stage is a small async function the runner can call independently.
Keep each one idempotent so retries resume from the first missing output.
"""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ai.gemini import call_gemini
from media.store import get_media_store

from .schemas import LANE_B_SCHEMA, analyze_prompt, validate_analyze
from .transcode import extract_frame, ffprobe, transcode_h264

logger = logging.getLogger("firstshift.lessons.pipeline")


# Allowed test-only env fail-point. Set to one of:
#   "converting" | "analyzing" | "extracting_frames" | "publishing"
_FAIL_ENV = "LESSONS_FORCE_FAIL_STAGE"


def _maybe_force_fail(stage: str) -> None:
    if os.environ.get(_FAIL_ENV, "").strip() == stage:
        raise RuntimeError(f"forced failure (LESSONS_FORCE_FAIL_STAGE={stage})")


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- Stage: convert ----------
async def stage_convert(assembled_path: str) -> tuple[str, float, int]:
    """Transcode an assembled upload to H.264 ≤18 MB, store in MediaStore.

    Returns (video_id, duration_s, size_bytes).
    """
    _maybe_force_fail("converting")

    probe = await ffprobe(assembled_path)
    if not probe.has_video_stream:
        raise ValueError("UNSUPPORTED_MEDIA: not a video file")
    duration_s = probe.duration_s
    if duration_s <= 0:
        raise ValueError("UNSUPPORTED_MEDIA: zero-duration video")
    if duration_s > 120.0:
        raise ValueError("TOO_LONG: Video is longer than 2 minutes")

    tmp_out = Path(tempfile.gettempdir()) / f"lessons-{uuid.uuid4().hex}.mp4"
    try:
        size = await transcode_h264(assembled_path, str(tmp_out), duration_s=duration_s)
        with open(tmp_out, "rb") as f:
            data = f.read()
        store = get_media_store()
        video_id = await store.save(data, "video/mp4", filename="lesson.mp4")
        return video_id, duration_s, size
    finally:
        try:
            if tmp_out.exists():
                tmp_out.unlink()
        except Exception:  # noqa: BLE001
            pass


# ---------- Stage: analyze ----------
async def stage_analyze(video_id: str, duration_s: float) -> tuple[dict, list[dict]]:
    """Run Gemini analysis + validation, retry once with error feedback.

    Returns (draft_dict, problems_list). Non-blocking problems are allowed to
    live on the draft; blocking ones must be fixed before publish.
    """
    _maybe_force_fail("analyzing")

    prompt = analyze_prompt(duration_s)
    raw = await call_gemini(
        prompt=prompt,
        media_uuids=[video_id],
        response_schema=LANE_B_SCHEMA,
        fps=1,
    )
    draft, problems = validate_analyze(raw, duration_s)
    blocking = [p for p in problems if p.get("blocking")]
    if blocking:
        # Retry once, surfacing the specific problems.
        detail = "; ".join(f"{p['where']}: {p['message']}" for p in blocking[:6])
        retry_prompt = (
            prompt
            + " Your previous response had problems: "
            + detail
            + ". Fix all of them and return a valid JSON per the schema."
        )
        raw2 = await call_gemini(
            prompt=retry_prompt,
            media_uuids=[video_id],
            response_schema=LANE_B_SCHEMA,
            fps=1,
        )
        draft2, problems2 = validate_analyze(raw2, duration_s)
        # Prefer the retry only if it reduced blocking count.
        if sum(1 for p in problems2 if p.get("blocking")) < len(blocking):
            draft, problems = draft2, problems2

    return draft, problems


# ---------- Stage: extract frames ----------
async def stage_extract_frames(video_id: str, draft: dict) -> dict:
    """Pull a mid-point still for every step; writes `frame_id` on each step."""
    _maybe_force_fail("extracting_frames")

    store = get_media_store()
    stream, _ct, _fn = await store.get(video_id)

    # Pull the stored video to a temp file for seek-friendly extraction.
    tmp_src = Path(tempfile.gettempdir()) / f"lesson-src-{uuid.uuid4().hex}.mp4"
    with open(tmp_src, "wb") as f:
        async for chunk in stream:
            f.write(chunk)

    try:
        new_steps = []
        for step in draft.get("steps", []):
            start = float(step.get("start") or 0.0)
            end = float(step.get("end") or 0.0)
            mid = max(0.0, (start + end) / 2.0)
            tmp_jpg = Path(tempfile.gettempdir()) / f"frame-{uuid.uuid4().hex}.jpg"
            try:
                await extract_frame(str(tmp_src), mid, str(tmp_jpg))
                with open(tmp_jpg, "rb") as g:
                    data = g.read()
                frame_id = await store.save(data, "image/jpeg", filename="frame.jpg")
            finally:
                try:
                    if tmp_jpg.exists():
                        tmp_jpg.unlink()
                except Exception:  # noqa: BLE001
                    pass
            new_steps.append({**step, "frame_id": frame_id})
        return {**draft, "steps": new_steps}
    finally:
        try:
            if tmp_src.exists():
                tmp_src.unlink()
        except Exception:  # noqa: BLE001
            pass


async def regen_single_frame(video_id: str, start: float, end: float) -> str:
    """Regenerate ONE still frame for a step (midpoint of start/end)."""
    store = get_media_store()
    stream, _ct, _fn = await store.get(video_id)
    tmp_src = Path(tempfile.gettempdir()) / f"lesson-src-{uuid.uuid4().hex}.mp4"
    with open(tmp_src, "wb") as f:
        async for chunk in stream:
            f.write(chunk)
    try:
        mid = max(0.0, (float(start) + float(end)) / 2.0)
        tmp_jpg = Path(tempfile.gettempdir()) / f"frame-{uuid.uuid4().hex}.jpg"
        try:
            await extract_frame(str(tmp_src), mid, str(tmp_jpg))
            with open(tmp_jpg, "rb") as g:
                data = g.read()
            return await store.save(data, "image/jpeg", filename="frame.jpg")
        finally:
            try:
                if tmp_jpg.exists():
                    tmp_jpg.unlink()
            except Exception:  # noqa: BLE001
                pass
    finally:
        try:
            if tmp_src.exists():
                tmp_src.unlink()
        except Exception:  # noqa: BLE001
            pass
