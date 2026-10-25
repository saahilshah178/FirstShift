"""Lessons-pipeline ffprobe + transcode wrappers.

Thin wrapper around the shared `backend/media/encode.py` helper (Stage 1).
The Lessons pipeline enforces an 18 MB cap; otherwise it shares the exact
same codec/container/+faststart choices as every other write path.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from media.encode import EncodeError as FFToolError  # re-export for callers
from media.encode import encode_mp4, extract_frame as _encode_extract_frame

logger = logging.getLogger("firstshift.lessons.transcode")

# Lessons pipeline sizing — unchanged from pre-Stage-1 semantics.
MAX_OUTPUT_BYTES = 18 * 1024 * 1024
MAX_DURATION_S = 120.0


@dataclass
class ProbeResult:
    duration_s: float
    width: int
    height: int
    has_video_stream: bool
    container_format: str


async def _run(cmd: list[str], *, cwd: str | None = None) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout, stderr


async def ffprobe(path: str) -> ProbeResult:
    """Run ffprobe, return parsed metadata; raise FFToolError on failure."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    rc, stdout, stderr = await _run(cmd)
    if rc != 0:
        raise FFToolError(f"ffprobe failed: {stderr.decode('utf-8','replace')[:300]}")
    try:
        info = json.loads(stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise FFToolError(f"ffprobe output not JSON: {exc}") from exc

    streams = info.get("streams") or []
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    if not video_streams:
        return ProbeResult(0.0, 0, 0, False, str((info.get("format") or {}).get("format_name") or ""))

    vs = video_streams[0]
    dur = float((info.get("format") or {}).get("duration") or vs.get("duration") or 0.0)
    width = int(vs.get("width") or 0)
    height = int(vs.get("height") or 0)
    fmt = str((info.get("format") or {}).get("format_name") or "")
    return ProbeResult(dur, width, height, True, fmt)


async def transcode_h264(src: str, dst: str, *, duration_s: float) -> int:
    """Transcode `src` → `dst` via the shared single-encoder helper.

    Preserves the pre-Stage-1 Lessons sizing: short side 720 (via long-side
    cap in the shared helper), AAC 64k mono, 18 MB cap honoured by the
    helper's bitrate-targeted retry.
    """
    result = await encode_mp4(
        src, dst,
        target_bytes=MAX_OUTPUT_BYTES,
        long_side=720,
        audio_bitrate="64k",
        duration_s=duration_s,
    )
    return result.bytes_written


async def extract_frame(src_path: str, at_s: float, dst_path: str) -> None:
    """Thin re-export of `media.encode.extract_frame` so callers don't have to switch imports."""
    await _encode_extract_frame(src_path, at_s, dst_path)
