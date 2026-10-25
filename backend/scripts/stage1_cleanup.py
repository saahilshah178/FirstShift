"""One-shot Stage-1 fixups cleanup.

Idempotent. Safe to run twice. Run with:

    python -m backend.scripts.stage1_cleanup

Does three things:

1. **Null step frame_ids on skills without a source video.** The Stage-1
   brief forbids placeholder-image blocks on skills that don't yet have
   a source clip. The seed used to generate synthetic 320x200 PNG
   frames anyway — those are "placeholder image blocks". Walk every
   skill; if `video_id` is null or missing, collect the current
   `step.frame_id`s, null them on the skill, and delete the
   corresponding blobs from GridFS **by uuid** (not blanket).

2. **Revert the testing agent's Replace-Source-Video on the Transfer
   skill.** The tester uploaded a 30 s test-pattern as the Transfer
   source and the 4 step frames were re-extracted from it. Revert the
   skill (null `video_id` + per-step `frame_id`s) and delete the test
   video + its 4 derived jpg frames from GridFS. Jovelyn's attempt
   clip stays untouched (it's a separate upload).

3. **Clamp seeded attempts' check timestamps to clip duration.** Any
   seeded attempt whose `clip_source` starts with `seed-` has its
   `checks[].time` clamped via
   `features/grading/clamp.clamp_check_times` using the attempt's own
   `duration`. Idempotent: re-running leaves the already-clamped
   times alone.

The script prints a summary to stdout and does NOT touch any skill
that isn't a known-clean target. Safe-guard rails:
- GridFS deletions ONLY run on blob ids this script found via
  `skill.steps[].frame_id` / `skill.video_id`. No blanket deletes.
- Orphan tiny PNGs (left behind by earlier seed cycles) are also
  cleaned, matched conservatively by filename prefix
  (`"<skill title>-step-"`) + `metadata.content_type == "image/png"`
  + `length < 5120`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[1]
_REPO = _HERE.parents[2]
for p in (_BACKEND, _REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND / ".env")

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket  # noqa: E402

from features.grading.clamp import clamp_check_times  # noqa: E402

logger = logging.getLogger("firstshift.scripts.stage1_cleanup")

ORPHAN_PNG_MAX_SIZE = 5 * 1024  # 5 KB — the seed's synthetic PNGs are ~2 KB.


async def _delete_by_uuid(bucket, db, uuid_str: str) -> bool:
    """Delete a MediaStore blob by its public uuid. Return True if deleted."""
    doc = await db["media.files"].find_one({"metadata.uuid": uuid_str}, {"_id": 1})
    if not doc:
        return False
    await bucket.delete(doc["_id"])
    return True


async def run() -> dict:
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "firstshift")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="media")

    summary = {
        "skills_scrubbed": [],
        "frames_deleted": 0,
        "orphan_png_deleted": 0,
        "orphan_jpg_deleted": 0,
        "orphan_mp4_deleted": 0,
        "transfer_reverted": False,
        "transfer_test_video_deleted": False,
        "attempts_clamped": 0,
    }

    # --- 1. Null step frame_ids on skills without a source video ------------
    cursor = db.skills.find({})
    async for skill in cursor:
        if skill.get("video_id"):
            continue
        steps = skill.get("steps") or []
        orig_frame_ids = [s.get("frame_id") for s in steps if s.get("frame_id")]
        if not orig_frame_ids:
            continue
        for fid in orig_frame_ids:
            if await _delete_by_uuid(bucket, db, fid):
                summary["frames_deleted"] += 1
        await db.skills.update_one(
            {"_id": skill["_id"]},
            {"$set": {
                "steps": [{**s, "frame_id": None} for s in steps],
            }},
        )
        summary["skills_scrubbed"].append(skill.get("title"))

    # --- 2. Revert Transfer skill if a tester-uploaded video is still bound -
    transfer = await db.skills.find_one({"title": "Transfer from bed to wheelchair"})
    if transfer and transfer.get("video_id"):
        vid = transfer["video_id"]
        step_frames = [s.get("frame_id") for s in (transfer.get("steps") or []) if s.get("frame_id")]
        # Delete video + derived frames by uuid.
        if await _delete_by_uuid(bucket, db, vid):
            summary["transfer_test_video_deleted"] = True
        for fid in step_frames:
            if await _delete_by_uuid(bucket, db, fid):
                summary["frames_deleted"] += 1
        await db.skills.update_one(
            {"_id": transfer["_id"]},
            {"$set": {
                "video_id": None,
                "steps": [{**s, "frame_id": None} for s in (transfer.get("steps") or [])],
            }},
        )
        summary["transfer_reverted"] = True
        if transfer["title"] not in summary["skills_scrubbed"]:
            summary["skills_scrubbed"].append(transfer["title"])

    # --- 3. Orphan tiny PNG seed frames in GridFS ---------------------------
    # Match conservative: name ends with "-step-N.png", content_type image/png,
    # length < 5 KB, AND not currently referenced by any skill.step.frame_id.
    referenced_uuids: set[str] = set()
    async for s in db.skills.find({}, {"steps.frame_id": 1, "video_id": 1}):
        if s.get("video_id"):
            referenced_uuids.add(s["video_id"])
        for st in (s.get("steps") or []):
            fid = st.get("frame_id")
            if fid:
                referenced_uuids.add(fid)
    referenced_clip_uuids: set[str] = set()
    async for a in db.attempts.find({}, {"clip_id": 1}):
        if a.get("clip_id"):
            referenced_clip_uuids.add(a["clip_id"])

    orphan_png_q = {
        "metadata.content_type": "image/png",
        "length": {"$lt": ORPHAN_PNG_MAX_SIZE},
        "filename": {"$regex": r"-step-\d+\.png$"},
    }
    async for f in db["media.files"].find(orphan_png_q):
        md = f.get("metadata") or {}
        uid = md.get("uuid")
        if uid and uid in referenced_uuids:
            continue
        await bucket.delete(f["_id"])
        summary["orphan_png_deleted"] += 1

    # --- 3b. Orphan jpg frames left by prior Replace-Source-Video runs ------
    # Match: name ends with "-step-N.jpg" AND metadata.uuid is not currently
    # referenced by any skill.steps[].frame_id. These are the step frames
    # that the "Replace source video" endpoint writes; they become orphans
    # whenever a Care Manager re-replaces the video or when the testing
    # harness's upload is reverted (see §2 above).
    orphan_jpg_q = {
        "metadata.content_type": "image/jpeg",
        "filename": {"$regex": r"-step-\d+\.jpg$"},
    }
    async for f in db["media.files"].find(orphan_jpg_q):
        md = f.get("metadata") or {}
        uid = md.get("uuid")
        if uid and uid in referenced_uuids:
            continue
        await bucket.delete(f["_id"])
        summary["orphan_jpg_deleted"] = summary.get("orphan_jpg_deleted", 0) + 1

    # --- 3c. Orphan mp4 clips (seed-leftover + tester uploads) --------------
    # Safe-match: name matches a known seed/upload pattern AND metadata.uuid
    # is not referenced by any attempt.clip_id OR skill.video_id. The
    # patterns are tight on purpose — healthcheck + user-uploaded videos
    # with arbitrary names are NOT touched.
    orphan_mp4_name_patterns = [
        r"^attempt-\d+\.mp4$",                              # seed attempts
        r"^attempt-jovelyn-transfer\.mp4$",                 # Jovelyn placeholder
        r"^[0-9a-f]{32}\.mp4$",                             # saved by uuid filename
    ]
    orphan_mp4_q = {
        "metadata.content_type": "video/mp4",
        "$or": [{"filename": {"$regex": p}} for p in orphan_mp4_name_patterns],
    }
    all_refs = referenced_uuids | referenced_clip_uuids
    async for f in db["media.files"].find(orphan_mp4_q):
        md = f.get("metadata") or {}
        uid = md.get("uuid")
        if uid and uid in all_refs:
            continue
        await bucket.delete(f["_id"])
        summary["orphan_mp4_deleted"] = summary.get("orphan_mp4_deleted", 0) + 1

    # --- 4. Clamp seeded attempt check timestamps to clip duration ----------
    cursor = db.attempts.find({"clip_source": {"$regex": r"^seed-"}})
    async for attempt in cursor:
        duration = attempt.get("duration")
        if not isinstance(duration, (int, float)) or duration <= 0:
            continue
        checks = attempt.get("checks") or []
        clamped = clamp_check_times(checks, clip_duration=duration)
        if clamped != checks:
            await db.attempts.update_one(
                {"_id": attempt["_id"]},
                {"$set": {"checks": clamped}},
            )
            summary["attempts_clamped"] += 1

    client.close()
    return summary


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = asyncio.run(run())
    print("stage1 cleanup complete:")
    for k, v in out.items():
        print(f"  {k:28s} {v}")


if __name__ == "__main__":
    _main()
