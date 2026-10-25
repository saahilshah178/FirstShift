"""GridFS-backed media store.

Single interface for storing and retrieving user media. UUIDs are
opaque (`uuid4().hex`) so collection internals are not leaked to callers.
"""
from __future__ import annotations

import os
import uuid
from typing import AsyncIterator

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorGridFSBucket,
)


class MediaStore:
    """Async GridFS wrapper.

    Public interface:
        - save(file_bytes, content_type, filename=None) -> uuid_str
        - get(uuid_str) -> (async_stream, content_type, filename)        [legacy]
        - open(uuid_str) -> {gridfs_id, length, content_type, filename}
        - read_full(info)             -> async bytes iterator
        - read_range(info, start, end)-> async bytes iterator (inclusive end)
        - replace_blob(uuid_str, new_bytes, content_type?, filename?)
    """

    def __init__(self, bucket: AsyncIOMotorGridFSBucket):
        self._bucket = bucket

    async def save(
        self,
        file_bytes: bytes,
        content_type: str,
        filename: str | None = None,
    ) -> str:
        uid = uuid.uuid4().hex
        meta = {"uuid": uid, "content_type": content_type}
        await self._bucket.upload_from_stream(
            filename or uid,
            file_bytes,
            metadata=meta,
        )
        return uid

    async def open(self, uuid_str: str) -> dict:
        """Return `{gridfs_id, length, content_type, filename}` for `uuid_str`.
        Raises `FileNotFoundError` when the media is not present."""
        cursor = self._bucket.find({"metadata.uuid": uuid_str}).limit(1)
        docs = await cursor.to_list(length=1)
        if not docs:
            raise FileNotFoundError(uuid_str)
        doc = docs[0]
        return {
            "gridfs_id": doc["_id"],
            "length": int(doc.get("length") or 0),
            "content_type": (doc.get("metadata") or {}).get(
                "content_type", "application/octet-stream"
            ),
            "filename": doc.get("filename") or uuid_str,
        }

    async def read_full(self, info: dict) -> AsyncIterator[bytes]:
        """Yield the entire blob, chunk by chunk."""
        stream = await self._bucket.open_download_stream(info["gridfs_id"])
        try:
            while True:
                chunk = await stream.readchunk()
                if not chunk:
                    break
                yield chunk
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result

    async def read_range(
        self,
        info: dict,
        start: int,
        end: int,
    ) -> AsyncIterator[bytes]:
        """Yield bytes for the inclusive range `[start, end]`.

        Uses forward-skip through the gridfs chunks (255 KB default), which is
        correct but reads up to `start` bytes of data before yielding. For the
        file sizes we handle (≤18 MB after lessons transcode, ≤50 MB upload cap)
        the extra I/O is negligible on local disk; swapping to the native
        `stream.seek(start)` call is a future optimisation if it becomes a hot
        path.
        """
        stream = await self._bucket.open_download_stream(info["gridfs_id"])
        try:
            pos = 0
            remaining = end - start + 1
            while remaining > 0:
                chunk = await stream.readchunk()
                if not chunk:
                    break
                clen = len(chunk)
                if pos + clen <= start:
                    pos += clen
                    continue
                offset_in_chunk = max(0, start - pos)
                take_end = min(clen, offset_in_chunk + remaining)
                piece = chunk[offset_in_chunk:take_end]
                if piece:
                    yield piece
                    remaining -= len(piece)
                pos += clen
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result

    async def replace_blob(
        self,
        uuid_str: str,
        new_bytes: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> None:
        """Replace the raw bytes behind `uuid_str` while keeping the public id.

        Used by `scripts/faststart_backfill.py` to re-encode existing videos
        in-place. Internally deletes the old gridfs file and uploads a new one
        with the same metadata uuid.
        """
        info = await self.open(uuid_str)
        await self._bucket.delete(info["gridfs_id"])
        meta = {
            "uuid": uuid_str,
            "content_type": content_type or info["content_type"],
        }
        await self._bucket.upload_from_stream(
            filename or info["filename"],
            new_bytes,
            metadata=meta,
        )

    async def get(self, uuid_str: str) -> tuple[AsyncIterator[bytes], str, str]:
        """Legacy entry point. Returns `(iterator, content_type, filename)`."""
        info = await self.open(uuid_str)

        async def _iter() -> AsyncIterator[bytes]:
            async for piece in self.read_full(info):
                yield piece

        return _iter(), info["content_type"], info["filename"]


# ---- Module singleton bound to the app's Mongo DB ----
_mongo_client: AsyncIOMotorClient | None = None
_media_store: MediaStore | None = None


def get_media_store() -> MediaStore:
    """Return a lazily-constructed MediaStore bound to the default DB."""
    global _mongo_client, _media_store
    if _media_store is None:
        mongo_url = os.environ["MONGO_URL"]
        db_name = os.environ.get("DB_NAME", "firstshift")
        _mongo_client = AsyncIOMotorClient(mongo_url)
        bucket = AsyncIOMotorGridFSBucket(
            _mongo_client[db_name], bucket_name="media"
        )
        _media_store = MediaStore(bucket)
    return _media_store
