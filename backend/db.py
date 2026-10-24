"""Shared Mongo client bound to the configured DB.

Imported by feature routers so they don't each spin up their own
`AsyncIOMotorClient`. The media store already owns its own client
(for GridFS); this one is for regular collections.
"""
from __future__ import annotations

import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        _db = _client[os.environ.get("DB_NAME", "firstshift")]
    return _db
