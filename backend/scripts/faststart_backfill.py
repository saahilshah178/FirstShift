"""Backfill `+faststart` on every stored video in GridFS.

Mobile Safari and some Android browsers refuse to start playing an mp4
when the `moov` atom lives at the tail of the file (iPad/iPhone Safari
needs the moov in the first ~1 MB to progressive-play). Our newer
`lessons/record` pipeline sets `-movflags +faststart`, but older seeds
and grading uploads did not.

Usage::

    python -m scripts.faststart_backfill          # inside /app/backend
    # OR
    python /app/backend/scripts/faststart_backfill.py

Idempotent: a second run skips files whose `moov` is already in the
first 1 MB (fast cheap check — no re-encode).
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path


_HEADER_SCAN_BYTES = 1 * 1024 * 1024  # 1 MB


def _load_env() -> None:
    env_path = Path("/app/backend/.env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _is_faststart(path: str) -> bool:
    """Return True if the `moov` atom appears in the first `_HEADER_SCAN_BYTES`."""
    with open(path, "rb") as f:
        head = f.read(_HEADER_SCAN_BYTES)
    return b"moov" in head


def _reencode(src: str, dst: str) -> None:
    """Stream-copy the input with `+faststart`. No re-encoding of A/V."""
    subprocess.check_call(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", src,
            "-c", "copy",
            "-movflags", "+faststart",
            dst,
        ],
        timeout=120,
    )


async def main() -> int:
    _load_env()
    sys.path.insert(0, "/app/backend")
    # Import after env is loaded so Motor binds correctly.
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket  # noqa: E402

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("faststart")

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "firstshift")]
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="media")

    processed = 0
    migrated = 0
    skipped = 0
    errors = 0

    cursor = db["media.files"].find({
        "metadata.content_type": {"$regex": "^video/"},
    })
    rows = await cursor.to_list(length=10000)
    log.info("scanning %d video rows", len(rows))

    for doc in rows:
        processed += 1
        meta = doc.get("metadata") or {}
        uid = meta.get("uuid")
        content_type = meta.get("content_type") or "video/mp4"
        if not uid:
            log.warning("row _id=%s missing metadata.uuid; skipping", doc.get("_id"))
            skipped += 1
            continue
        if int(doc.get("length") or 0) == 0:
            log.info("[skip-empty]  %s  (0 bytes)", uid)
            skipped += 1
            continue

        # Download to a temp file.
        tmp_in = Path(tempfile.gettempdir()) / f"fs-in-{uid}.mp4"
        tmp_out = Path(tempfile.gettempdir()) / f"fs-out-{uid}.mp4"
        try:
            stream = await bucket.open_download_stream(doc["_id"])
            with open(tmp_in, "wb") as f:
                while True:
                    chunk = await stream.readchunk()
                    if not chunk:
                        break
                    f.write(chunk)
            close = getattr(stream, "close", None)
            if close is not None:
                res = close()
                if hasattr(res, "__await__"):
                    await res

            if _is_faststart(str(tmp_in)):
                log.info("[already]     %s  %.1f MB", uid, int(doc.get("length") or 0) / 1024 / 1024)
                skipped += 1
                continue

            # Non-mp4 containers (webm, mov) don't have `moov`; skip them
            # — mobile browsers handle webm live-streaming fine.
            if content_type != "video/mp4":
                log.info("[non-mp4]     %s  %s", uid, content_type)
                skipped += 1
                continue

            try:
                _reencode(str(tmp_in), str(tmp_out))
            except subprocess.CalledProcessError as exc:
                log.error("[ffmpeg-fail] %s  rc=%s", uid, exc.returncode)
                errors += 1
                continue
            with open(tmp_out, "rb") as f:
                data = f.read()
            # Replace in-place via a direct bucket swap (keeps the metadata uuid stable).
            await bucket.delete(doc["_id"])
            await bucket.upload_from_stream(
                doc.get("filename") or f"{uid}.mp4",
                data,
                metadata={"uuid": uid, "content_type": content_type},
            )
            log.info("[faststart]   %s  %.1f MB", uid, len(data) / 1024 / 1024)
            migrated += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("[error]       %s: %s", uid, exc)
            errors += 1
        finally:
            for p in (tmp_in, tmp_out):
                try:
                    if p.exists():
                        p.unlink()
                except Exception:  # noqa: BLE001
                    pass

    log.info("done: processed=%d migrated=%d skipped=%d errors=%d",
             processed, migrated, skipped, errors)
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
