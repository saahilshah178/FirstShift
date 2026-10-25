"""Replace Jovelyn's seeded Transfer attempt clip with a cut from a real
source video.

Why this exists: the pod's egress IP is blocked by YouTube's video CDN,
so `yt-dlp` cannot fetch the Chippewa Valley CC BY source video from the
seed pipeline. This script runs manually after the user drops the real
file somewhere on the pod (or uploads it via the "Replace source video"
button on the Transfer skill — this helper swaps the attempt clip too
so Ready-to-sign gets the proper footage without a full re-seed).

Usage:
    python -m backend.scripts.reseed_jovelyn_from_source \\
        /path/to/transfer_source.mp4 [--start 12.0] [--duration 12.0]

Defaults: `--start 10 --duration 12`. The cut is encoded through
`media.encode.encode_mp4` (same path every other stored clip uses).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import tempfile
import uuid
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]  # /app/backend
_REPO = _HERE.parents[2]  # /app
for p in (_BACKEND, _REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND / ".env")

import os  # noqa: E402

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket  # noqa: E402

from media.encode import cut_segment  # noqa: E402
from media.store import MediaStore  # noqa: E402
from features.grading.clamp import clamp_check_times  # noqa: E402

logger = logging.getLogger("firstshift.scripts.reseed_jovelyn")


async def run(source_path: Path, *, start_s: float, duration_s: float) -> dict:
    if not source_path.exists():
        raise SystemExit(f"source video not found: {source_path}")

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "firstshift")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="media")
    store = MediaStore(bucket)

    caregiver = await db.caregivers.find_one(
        {"name": "Jovelyn Santos"}, {"_id": 1}
    )
    if not caregiver:
        raise SystemExit("Jovelyn Santos not found; run seed first.")

    attempt = await db.attempts.find_one(
        {"caregiver_id": caregiver["_id"], "clip_source": "seed-transfer-placeholder"},
        sort=[("created_at", -1)],
    )
    if not attempt:
        raise SystemExit(
            "Jovelyn's seed-transfer-placeholder attempt not found; "
            "run seed first, then re-run this script."
        )

    with tempfile.TemporaryDirectory(prefix="fs-reseed-") as tmp:
        dst = Path(tmp) / "jovelyn_cut.mp4"
        result = await cut_segment(
            source_path, dst, start_s=start_s, duration_s=duration_s
        )
        clip_bytes = dst.read_bytes()
        new_clip_id = await store.save(
            clip_bytes, "video/mp4", filename=f"{uuid.uuid4().hex}.mp4"
        )

    # Re-clamp the seeded check timestamps to the new clip length so a
    # longer real clip pushes them back out (and a shorter one clamps
    # them in).
    checks = clamp_check_times(
        attempt.get("checks") or [],
        clip_duration=duration_s,
    )
    await db.attempts.update_one(
        {"_id": attempt["_id"]},
        {"$set": {
            "clip_id": new_clip_id,
            "clip_source": "cut-from-source",
            "duration": round(duration_s, 3),
            "checks": checks,
        }},
    )
    client.close()
    return {
        "attempt_id": attempt["_id"],
        "new_clip_id": new_clip_id,
        "bytes_written": result.bytes_written,
    }


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Path to the source video on disk")
    parser.add_argument("--start", type=float, default=10.0, help="Cut start in seconds")
    parser.add_argument("--duration", type=float, default=12.0, help="Cut duration in seconds")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = asyncio.run(run(args.source, start_s=args.start, duration_s=args.duration))
    print("reseed complete:")
    for k, v in out.items():
        print(f"  {k:16s} {v}")


if __name__ == "__main__":
    _main()
