"""Backfill `steps[].start`/`steps[].end` for seeded skills.

Context — Fix B (Batch-2 tightening):

Seeded skills were created directly (not through the lane-B lesson
pipeline) and some left `steps[].start` / `steps[].end` as `null`.
The validator (`features/lessons/schemas.py::validate_analyze`) treats
missing timestamps as blocking on edit → publish, so Care Managers who
try to edit such a skill cannot republish it.

Strategy (option 2 in the tightening brief): distribute step
timestamps evenly across the skill's expected clip duration.
  - If `video_id` is set and resolves to a readable blob in GridFS,
    `ffprobe` it to get the real duration.
  - Otherwise fall back to a default of 60 seconds (matches the
    tightening note's example).

For N steps and total duration D:
    step i (1-indexed) → start = (i - 1) * D / N
                         end   =  i      * D / N

Only steps with `start is None` OR `end is None` are patched. If a
skill is already fully timed it is left alone.

Idempotent — re-running after a successful pass finds nothing to
backfill.

Run with:
    python -m backend.scripts.backfill_seeded_timestamps
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket


DEFAULT_DURATION_S = 60.0


async def _probe_video_duration(bucket: AsyncIOMotorGridFSBucket, video_id: str) -> float | None:
    """Return the duration in seconds of the GridFS blob tagged with `video_id`,
    or None if the blob is missing / ffprobe fails."""
    try:
        cursor = bucket.find({"metadata.uuid": video_id}).limit(1)
        docs = await cursor.to_list(length=1)
        if not docs:
            return None
        gridfs_id = docs[0]["_id"]
        stream = await bucket.open_download_stream(gridfs_id)
        try:
            with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
                tmp_path = tmp.name
                while True:
                    chunk = await stream.readchunk()
                    if not chunk:
                        break
                    tmp.write(chunk)
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
        try:
            out = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    tmp_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if out.returncode == 0 and out.stdout.strip():
                return float(out.stdout.strip())
            return None
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception as exc:  # noqa: BLE001
        print(f"  (probe failed for {video_id[:8]}: {exc})")
        return None


def _needs_backfill(steps: list) -> bool:
    for s in steps or []:
        if s.get("start") is None or s.get("end") is None:
            return True
    return False


async def main() -> int:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "firstshift")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="media")

    patched: list[tuple[str, str, int, float]] = []  # (skill_id, title, n_steps, duration)
    async for skill in db.skills.find({}):
        steps = skill.get("steps") or []
        if not steps or not _needs_backfill(steps):
            continue

        n = len(steps)
        duration = None
        if skill.get("video_id"):
            duration = await _probe_video_duration(bucket, skill["video_id"])
        if not duration or duration <= 0:
            duration = DEFAULT_DURATION_S

        per_step = duration / n
        new_steps = []
        for i, s in enumerate(steps, start=1):
            start = s.get("start")
            end = s.get("end")
            # Only overwrite the null side(s); if the pipeline left a real
            # value in one slot, keep it.
            if start is None:
                start = round((i - 1) * per_step, 2)
            if end is None:
                end = round(i * per_step, 2)
            new_steps.append({**s, "start": float(start), "end": float(end)})
        await db.skills.update_one(
            {"_id": skill["_id"]},
            {"$set": {"steps": new_steps}},
        )
        patched.append((skill["_id"], skill.get("title", "(unknown)"), n, duration))

    if not patched:
        print("[backfill_seeded_timestamps] nothing to backfill; every seeded skill is fully timed.")
    else:
        print(f"[backfill_seeded_timestamps] patched {len(patched)} skill(s):")
        for sid, title, n, duration in patched:
            per = duration / n
            print(
                f"  - {title!r} ({sid[:8]}): {n} steps across {duration:.1f}s "
                f"→ {per:.2f}s/step"
            )

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
