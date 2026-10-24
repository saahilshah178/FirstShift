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
        - get(uuid_str) -> (async_stream, content_type, filename)
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

    async def get(self, uuid_str: str) -> tuple[AsyncIterator[bytes], str, str]:
        """Return (chunk-iterator, content_type, filename). 404 if missing."""
        cursor = self._bucket.find({"metadata.uuid": uuid_str}).limit(1)
        docs = await cursor.to_list(length=1)
        if not docs:
            raise FileNotFoundError(uuid_str)
        doc = docs[0]
        stream = await self._bucket.open_download_stream(doc["_id"])
        content_type = (doc.get("metadata") or {}).get(
            "content_type", "application/octet-stream"
        )
        filename = doc.get("filename") or uuid_str

        async def _iter() -> AsyncIterator[bytes]:
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

        return _iter(), content_type, filename


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
