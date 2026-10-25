"""Single video encoding helper (Stage 1 — Media pipeline audit).

Every write path that stores a clip (seeds, grading uploads, lessons
transcode, "Replace source video") goes through `encode_mp4()`. The
output is always H.264 (yuv420p) + AAC + `+faststart`, long-side 720,
served with `Range` / `206 Partial Content` by `media/routes.py`.

Two modes:
- `target_bytes=None` (default): single-pass CRF 23 — grading / seed /
  replace_source_video size budget is loose enough for CRF to suffice.
- `target_bytes=N`: initial CRF 28 pass; if `os.path.getsize(dst) > N`
  a second bitrate-targeted pass runs. Used by the Lessons record
  pipeline (18 MB cap).

Why one helper: before Stage 1 we had two subprocesses in two
features (`features/grading/ingest.py::_transcode_to_mp4`,
`features/lessons/transcode.py::transcode_h264`) plus seed clips that
bypassed encoding entirely. See `docs/CHANGELOG.md` entry
"Stage 1: Demo data and content" for the audit.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("firstshift.media.encode")

DEFAULT_LONG_SIDE = 720
DEFAULT_AUDIO_BITRATE = "128k"
DEFAULT_CRF = "23"
BUDGET_CRF = "28"


class EncodeError(RuntimeError):
    pass


@dataclass
class EncodeResult:
    bytes_written: int
    long_side: int


async def _run(cmd: list[str]) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout, stderr


def _vf_long_side(long_side: int) -> str:
    """Scale filter: long side == `long_side` without upscaling, keep aspect, yuv420p."""
    return (
        f"scale='if(gt(iw,ih),min({long_side},iw),-2)':'if(gt(iw,ih),-2,min({long_side},ih))'"
        ",format=yuv420p"
    )


async def encode_mp4(
    src: str | os.PathLike,
    dst: str | os.PathLike,
    *,
    target_bytes: int | None = None,
    long_side: int = DEFAULT_LONG_SIDE,
    audio_bitrate: str = DEFAULT_AUDIO_BITRATE,
    duration_s: float | None = None,
) -> EncodeResult:
    """Encode `src` → `dst` as a browser-playable H.264/AAC mp4.

    Guarantees on `dst`:
    - H.264 (libx264), yuv420p pixel format.
    - AAC audio (if the source has audio).
    - Long side ≤ `long_side` (default 720), no upscale, aspect preserved.
    - `+faststart` so the moov atom sits at the head of the file.
    - When `target_bytes` is set, output file is ≤ that cap after the
      bitrate-targeted retry pass.

    Raises EncodeError on any ffmpeg failure.
    """
    src = str(src)
    dst = str(dst)
    vf = _vf_long_side(long_side)

    # Pass 1 — CRF (either default 23 or budget 28 if we have a cap).
    crf = BUDGET_CRF if target_bytes else DEFAULT_CRF
    cmd_crf = [
        "ffmpeg", "-y", "-v", "error",
        "-i", src,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", crf,
        "-c:a", "aac", "-b:a", audio_bitrate, "-ac", "1",
        "-movflags", "+faststart",
        dst,
    ]
    rc, _o, err = await _run(cmd_crf)
    if rc != 0:
        raise EncodeError(
            f"ffmpeg CRF pass failed: {err.decode('utf-8','replace')[:300]}"
        )

    size = os.path.getsize(dst)

    # Pass 2 only when a byte cap is set AND the first pass busted it.
    if target_bytes is not None and size > target_bytes:
        # Reserve 64 kbps for audio, 5% container overhead.
        if duration_s is None:
            duration_s = _ffprobe_duration(src) or 1.0
        overhead_bits = 64_000 * max(duration_s, 1.0)
        budget_bits = target_bytes * 8 * 0.95
        video_bits_total = max(
            budget_bits - overhead_bits, 150_000 * max(duration_s, 1.0)
        )
        video_bps = int(video_bits_total / max(duration_s, 1.0))
        video_bps = max(video_bps, 250_000)  # floor so it still plays
        cmd_bps = [
            "ffmpeg", "-y", "-v", "error",
            "-i", src,
            "-vf", vf,
            "-c:v", "libx264",
            "-b:v", f"{video_bps}",
            "-maxrate", f"{int(video_bps * 1.2)}",
            "-bufsize", f"{int(video_bps * 2)}",
            "-preset", "veryfast",
            "-c:a", "aac", "-b:a", audio_bitrate, "-ac", "1",
            "-movflags", "+faststart",
            dst,
        ]
        rc, _o, err = await _run(cmd_bps)
        if rc != 0:
            raise EncodeError(
                f"ffmpeg bitrate pass failed: {err.decode('utf-8','replace')[:300]}"
            )
        size = os.path.getsize(dst)
        if size > target_bytes:
            logger.warning(
                "encoded video still %d bytes after 2 passes (cap %d)",
                size, target_bytes,
            )

    return EncodeResult(bytes_written=size, long_side=long_side)


def _ffprobe_duration(path: str) -> float | None:
    """Synchronous duration probe for the rare case we don't know it."""
    import json
    import subprocess
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-print_format", "json",
                "-show_format", "-show_streams",
                path,
            ],
            check=False, capture_output=True, text=True, timeout=20,
        )
        if r.returncode != 0:
            return None
        info = json.loads(r.stdout or "{}")
        d = (info.get("format") or {}).get("duration")
        return float(d) if d is not None else None
    except Exception:  # noqa: BLE001
        return None


async def extract_frame(src_path: str | os.PathLike, at_s: float, dst_path: str | os.PathLike) -> None:
    """Extract a single JPEG from `src_path` at `at_s` seconds → `dst_path`."""
    at = max(0.0, float(at_s))
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{at:.2f}",
        "-i", str(src_path),
        "-frames:v", "1",
        "-q:v", "3",
        str(dst_path),
    ]
    rc, _o, err = await _run(cmd)
    if rc != 0 or not Path(dst_path).exists():
        raise EncodeError(
            f"frame extraction failed @ {at:.2f}s: {err.decode('utf-8','replace')[:300]}"
        )


async def cut_segment(
    src_path: str | os.PathLike,
    dst_path: str | os.PathLike,
    *,
    start_s: float,
    duration_s: float,
    long_side: int = DEFAULT_LONG_SIDE,
) -> EncodeResult:
    """Cut `[start_s, start_s + duration_s]` out of `src_path` → `dst_path`.

    Transcodes (not stream-copy) so the resulting mp4 is faststart-ready and
    truly starts at the requested timestamp (keyframe-independent). Shares
    the same codec choices as `encode_mp4` so every stored clip looks the
    same to the player.
    """
    src = str(src_path)
    dst = str(dst_path)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{max(0.0, float(start_s)):.2f}",
        "-i", src,
        "-t", f"{max(0.1, float(duration_s)):.2f}",
        "-vf", _vf_long_side(long_side),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", DEFAULT_CRF,
        "-c:a", "aac", "-b:a", DEFAULT_AUDIO_BITRATE, "-ac", "1",
        "-movflags", "+faststart",
        dst,
    ]
    rc, _o, err = await _run(cmd)
    if rc != 0:
        raise EncodeError(
            f"ffmpeg segment cut failed: {err.decode('utf-8','replace')[:300]}"
        )
    return EncodeResult(bytes_written=os.path.getsize(dst), long_side=long_side)
