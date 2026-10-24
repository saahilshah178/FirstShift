"""ffprobe + ffmpeg wrappers for the lessons pipeline.

System binaries (`ffmpeg`, `ffprobe`) are required and already present on
the pod. If missing, see `docs/merge/lessons.md`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("firstshift.lessons.transcode")

MAX_OUTPUT_BYTES = 18 * 1024 * 1024  # 18 MB cap on the stored compressed video
MAX_DURATION_S = 120.0


class FFToolError(RuntimeError):
    pass


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
    """Run ffprobe and return parsed metadata. Raises FFToolError on failure."""
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
    """Transcode `src` → `dst` as H.264 mp4 ≤ MAX_OUTPUT_BYTES.

    - Short side 720 (never upscale), keep aspect, auto-rotate.
    - AAC 64k, +faststart.
    - Tries CRF 28 first; if the output is over cap, re-encodes with a
      bitrate target computed from duration (reserving 64 kbps for audio).

    Returns the final file size in bytes. Raises FFToolError on failure.
    """
    # Short side 720 without upscale:
    #   if landscape (iw>ih): clamp height to min(720,ih), width -2.
    #   else:                 clamp width  to min(720,iw), height -2.
    vf = (
        "scale='if(gt(iw,ih),-2,min(720,iw))':'if(gt(iw,ih),min(720,ih),-2)'"
        ",format=yuv420p"
    )

    # Pass 1: CRF-based.
    cmd1 = [
        "ffmpeg", "-y", "-v", "error",
        "-i", src,
        "-vf", vf,
        "-c:v", "libx264", "-crf", "28", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "64k", "-ac", "1",
        "-movflags", "+faststart",
        dst,
    ]
    rc, _o, err = await _run(cmd1)
    if rc != 0:
        raise FFToolError(f"ffmpeg CRF pass failed: {err.decode('utf-8','replace')[:300]}")

    size = os.path.getsize(dst)
    if size <= MAX_OUTPUT_BYTES:
        return size

    # Pass 2: target bitrate so (video+audio)*duration ≤ cap.
    overhead_bits = 64_000 * max(duration_s, 1.0)  # audio
    budget_bits = MAX_OUTPUT_BYTES * 8 * 0.95       # 5% container overhead
    video_bits_total = max(budget_bits - overhead_bits, 150_000 * max(duration_s, 1.0))
    video_bps = int(video_bits_total / max(duration_s, 1.0))
    video_bps = max(video_bps, 250_000)             # floor so it still plays

    cmd2 = [
        "ffmpeg", "-y", "-v", "error",
        "-i", src,
        "-vf", vf,
        "-c:v", "libx264",
        "-b:v", f"{video_bps}",
        "-maxrate", f"{int(video_bps*1.2)}",
        "-bufsize", f"{int(video_bps*2)}",
        "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "64k", "-ac", "1",
        "-movflags", "+faststart",
        dst,
    ]
    rc, _o, err = await _run(cmd2)
    if rc != 0:
        raise FFToolError(f"ffmpeg bitrate pass failed: {err.decode('utf-8','replace')[:300]}")

    size = os.path.getsize(dst)
    if size > MAX_OUTPUT_BYTES:
        logger.warning("compressed video still %d bytes after 2 passes (cap %d)", size, MAX_OUTPUT_BYTES)
    return size


async def extract_frame(src_path: str, at_s: float, dst_path: str) -> None:
    """Extract a single JPEG at `at_s` from `src_path` → `dst_path`."""
    at = max(0.0, float(at_s))
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{at:.2f}",
        "-i", src_path,
        "-frames:v", "1",
        "-q:v", "3",
        dst_path,
    ]
    rc, _o, err = await _run(cmd)
    if rc != 0 or not Path(dst_path).exists():
        raise FFToolError(f"frame extraction failed @ {at:.2f}s: {err.decode('utf-8','replace')[:300]}")
