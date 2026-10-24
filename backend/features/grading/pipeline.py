"""Lane-B grade_clip pipeline (initial, single-run version).

Stage 2: proves end-to-end Gemini wiring — extracts frames at 2 fps,
one Gemini call with the Lane-B prompt and schema, maps the response
back into the contract shape. The adaptive 3-run logic is added in
Stage 4 of this branch.

Transcode happens in `.ingest` before `grade_clip_pipeline` is called;
this module only consumes a stored mp4 UUID.
"""
from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from ai.gemini import call_gemini
from db import get_db
from media.store import get_media_store

logger = logging.getLogger("firstshift.grading.pipeline")


class GradingError(RuntimeError):
    """Raised when grading cannot produce a valid result."""


# ---- Lane B prompt + schema ----
# NOTE: prompt text is reproduced verbatim from the feature brief.
LANE_B_PROMPT_TEMPLATE = (
    "Input: a skill's ordered checks [{id, description, safety_critical}] "
    "and timestamped frames from the clip.\n"
    "Per check, decide:\n"
    "- \"passed\": you can see it happen, in the right order.\n"
    "- \"missed\": you can see it didn't happen, or it happened out of order.\n"
    "- \"unsure\": the angle, lighting, framing or blur hides it.\n"
    "Return JSON only:\n"
    "{\"checks\":[{\"id\":\"...\",\"result\":\"passed|missed|unsure\",\"time\":\"m:ss.s\",\"seen\":\"one short sentence\"}],"
    "\"overall\":\"pass|retry|retake\",\"message_for_caregiver\":\"one sentence in {language}\"}\n"
    "\"time\" is the frame label where the step happened or should have happened.\n"
    "overall: \"retake\" if any safety-critical check is unsure, else \"retry\" "
    "if any check is missed, else \"pass\".\n"
    "Never guess; judge only what is visible in the frames."
)

LANE_B_SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "result": {"type": "string", "enum": ["passed", "missed", "unsure"]},
                    "time": {"type": "string"},
                    "seen": {"type": "string"},
                },
                "required": ["id", "result", "time", "seen"],
            },
        },
        "overall": {"type": "string", "enum": ["pass", "retry", "retake"]},
        "message_for_caregiver": {"type": "string"},
    },
    "required": ["checks", "overall", "message_for_caregiver"],
}

LANGUAGE_NAMES = {"en": "English", "es": "Spanish", "tl": "Tagalog"}


# ---- helpers ----
def _label_for(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}:{s:04.1f}"


def _parse_label(label: str) -> float | None:
    try:
        m, s = label.split(":")
        return int(m) * 60 + float(s)
    except Exception:  # noqa: BLE001
        return None


async def _write_clip_tempfile(clip_id: str, dest_dir: Path) -> Path:
    store = get_media_store()
    stream, content_type, filename = await store.get(clip_id)
    out = dest_dir / "clip.mp4"
    with out.open("wb") as fh:
        async for chunk in stream:
            fh.write(chunk)
    return out


def _ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True, capture_output=True, text=True, timeout=30,
    )
    return float((r.stdout or "0").strip() or "0")


def _ffmpeg_extract_frames(
    clip_path: Path, out_dir: Path, *, fps: float = 2.0, offset: float = 0.0,
) -> list[tuple[float, Path]]:
    """Extract JPEG frames and burn a label on each.

    Returns [(timestamp_seconds, path), ...] in order.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    # Determine duration so we can pre-compute labels (ffmpeg's drawtext
    # with %{pts} is unreliable across versions on arm64; we post-label
    # instead).
    duration = _ffprobe_duration(clip_path)
    # Build the raw frame pattern.
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{offset:.3f}",
        "-i", str(clip_path),
        "-vf", f"fps={fps},scale='if(gt(iw,ih),640,-2)':'if(gt(iw,ih),-2,640)'",
        "-q:v", "4",
        str(out_dir / "frame_%04d.jpg"),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    frames: list[tuple[float, Path]] = []
    for i, p in enumerate(sorted(out_dir.glob("frame_*.jpg"))):
        t = offset + i / fps
        if t > duration + 0.05:
            break
        frames.append((t, p))
    return frames


def _overlay_label(image_bytes: bytes, label: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont  # type: ignore
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22
        )
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    pad = 6
    try:
        tw, th = draw.textbbox((0, 0), label, font=font)[2:]
    except Exception:  # noqa: BLE001
        tw, th = (len(label) * 10, 20)
    draw.rectangle([(0, 0), (tw + pad * 2, th + pad * 2)], fill=(0, 0, 0))
    draw.text((pad, pad), label, fill=(255, 255, 255), font=font)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()


async def _upload_labeled_frames(
    frames: list[tuple[float, Path]],
) -> list[tuple[str, float, str]]:
    """Overlay labels, upload each to MediaStore, return [(uuid, t, label)]."""
    store = get_media_store()
    out: list[tuple[str, float, str]] = []
    for t, path in frames:
        label = _label_for(t)
        with path.open("rb") as fh:
            raw = fh.read()
        labeled = _overlay_label(raw, label)
        uid = await store.save(labeled, "image/jpeg", filename=f"{label}.jpg")
        out.append((uid, t, label))
    return out


def _build_prompt(
    skill: dict,
    labels: list[str],
    language_name: str,
) -> str:
    checks_payload = [
        {"id": c["id"], "description": c["description"],
         "safety_critical": bool(c.get("safety_critical", False))}
        for c in skill.get("checks", [])
    ]
    header = LANE_B_PROMPT_TEMPLATE.replace("{language}", language_name)
    return (
        header
        + "\n\nChecks (ordered):\n" + json.dumps(checks_payload, ensure_ascii=False)
        + "\n\nFrame labels in order (m:ss.s):\n" + ", ".join(labels)
    )


# ---- main entry point ----
async def grade_clip_pipeline(
    skill_id: str, caregiver_id: str, clip_id: str,
) -> dict:
    """Single-run Lane-B grade. Stage 4 upgrades this to adaptive 3-run."""
    db = get_db()
    skill = await db.skills.find_one({"_id": skill_id})
    if not skill:
        raise GradingError(f"skill not found: {skill_id}")
    caregiver = await db.caregivers.find_one(
        {"_id": caregiver_id}, {"language": 1}
    )
    language = (caregiver or {}).get("language", "en")
    language_name = LANGUAGE_NAMES.get(language, "English")

    frame_ids_all: list[str] = []
    raw_runs: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="fs-grade-") as tmp:
        tmp_path = Path(tmp)
        clip_path = await _write_clip_tempfile(clip_id, tmp_path)
        frames = _ffmpeg_extract_frames(clip_path, tmp_path / "f0", offset=0.0)
        if not frames:
            raise GradingError("no frames extracted from clip")
        labeled = await _upload_labeled_frames(frames)
        frame_ids_all.extend([u for (u, _, _) in labeled])
        prompt = _build_prompt(skill, [lbl for (_, _, lbl) in labeled], language_name)
        raw = await call_gemini(
            prompt=prompt,
            media_uuids=[u for (u, _, _) in labeled],
            response_schema=LANE_B_SCHEMA,
        )
        raw_runs.append(raw)

    # Validate response.
    valid = _validate(raw, skill)
    if not valid:
        raise GradingError("invalid Gemini response for the only run")

    # Map to contract.
    return _assemble_contract(
        skill=skill,
        caregiver_id=caregiver_id,
        clip_id=clip_id,
        valid_runs=[raw],
        raw_runs=raw_runs,
        frame_ids=frame_ids_all,
    )


# ---- validation + aggregation ----
_ALLOWED_RESULT = {"passed", "missed", "unsure"}


def _validate(run: dict, skill: dict) -> bool:
    """Shape validity: every check id present, result in enum, time parses."""
    if not isinstance(run, dict):
        return False
    checks = run.get("checks")
    if not isinstance(checks, list):
        return False
    skill_ids = [c["id"] for c in skill.get("checks", [])]
    seen_ids = {c.get("id") for c in checks if isinstance(c, dict)}
    if seen_ids != set(skill_ids):
        return False
    for c in checks:
        if c.get("result") not in _ALLOWED_RESULT:
            return False
        if _parse_label(str(c.get("time", ""))) is None:
            return False
    return True


def _result_to_contract(r: str) -> str:
    return {"passed": "pass", "missed": "fail", "unsure": "unclear"}[r]


def _server_verdict(skill: dict, per_check: dict[str, str]) -> str:
    """verdict = retake if any safety-critical unsure; else retry if any missed; else pass."""
    sc_ids = {c["id"] for c in skill.get("checks", []) if c.get("safety_critical")}
    for cid, r in per_check.items():
        if cid in sc_ids and r == "unsure":
            return "retake"
    for r in per_check.values():
        if r == "missed":
            return "retry"
    return "pass"


def _verdict_to_overall(verdict: str) -> str:
    return {"pass": "pass", "retry": "fail", "retake": "needs_review"}[verdict]


def _assemble_contract(
    *,
    skill: dict,
    caregiver_id: str,
    clip_id: str,
    valid_runs: list[dict],
    raw_runs: list[dict],
    frame_ids: list[str],
) -> dict:
    runs_used = len(valid_runs)
    # Build per-check majority + time median + note.
    skill_checks = skill.get("checks", [])
    out_checks: list[dict] = []
    per_check_result: dict[str, str] = {}
    message_for_caregiver = ""
    for sc in skill_checks:
        cid = sc["id"]
        votes: list[tuple[str, float, str]] = []
        for run in valid_runs:
            for rc in run.get("checks", []):
                if rc.get("id") == cid:
                    t = _parse_label(str(rc.get("time", "")))
                    votes.append((rc["result"], float(t or 0.0), rc.get("seen") or ""))
                    break
        # Majority
        tally: dict[str, int] = {}
        for v, _, _ in votes:
            tally[v] = tally.get(v, 0) + 1
        if runs_used == 0 or not tally:
            result = "unsure"
        else:
            top = max(tally.items(), key=lambda kv: kv[1])
            # Majority rule: >50%. For 1-run that's just the only vote.
            # For 3-run equal split (1-1-1) → unsure.
            if top[1] * 2 > runs_used:
                result = top[0]
            else:
                result = "unsure"
        # Median time of agreeing runs.
        agreeing = [v for v in votes if v[0] == result]
        if agreeing:
            times = sorted(a[1] for a in agreeing)
            n = len(times)
            median = (times[n // 2] if n % 2 else 0.5 * (times[n // 2 - 1] + times[n // 2]))
            note = agreeing[0][2]
        else:
            median = 0.0
            note = (votes[0][2] if votes else "")
        safety_critical = bool(sc.get("safety_critical", False))
        out_checks.append({
            "id": cid,
            "description": sc.get("description", ""),
            "result": _result_to_contract(result),
            "time": round(median, 2),
            "seen": result != "unsure",
            "safety_critical": safety_critical,
            "note": note,
        })
        per_check_result[cid] = result

    verdict = _server_verdict(skill, per_check_result)
    overall = _verdict_to_overall(verdict)
    passed = sum(1 for c in out_checks if c["result"] == "pass")
    total = len(out_checks) or 1
    score = passed / total

    # Message: first run's message_for_caregiver.
    for run in valid_runs:
        m = run.get("message_for_caregiver")
        if isinstance(m, str) and m:
            message_for_caregiver = m
            break

    return {
        "skill_id": skill["_id"],
        "caregiver_id": caregiver_id,
        "clip_id": clip_id,
        "checks": out_checks,
        "overall": overall,
        "score": score,
        "created_at": None,  # caller fills
        "model": os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"),
        # additive keys
        "verdict": verdict,
        "message_for_caregiver": message_for_caregiver,
        "runs_used": runs_used,
        "graded_once": runs_used == 1,
        "raw_runs": raw_runs,
        "frame_ids": frame_ids,
    }
