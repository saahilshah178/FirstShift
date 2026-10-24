"""Channel service — swapped from the Phase-1 stub.

Logs every outbound message to the `messages` collection so the web
chat UI (and future WhatsApp outbound) renders from a single source
of truth. Signature preserved exactly:

    send_message(caregiver_id: str, text: str, media_url: str | None = None) -> dict

`media_url` is kept for backwards-compat with the stub signature; if
callers pass the string `/api/media/<uuid>` or just a bare uuid, we
extract the uuid and persist it as `media_id`.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import uuid
from datetime import datetime, timezone

from db import get_db

logger = logging.getLogger("firstshift.services.channel")


_UUID_RE = re.compile(r"([0-9a-fA-F]{32})")


def _extract_media_id(media_url: str | None) -> str | None:
    if not media_url:
        return None
    m = _UUID_RE.search(str(media_url))
    return m.group(1) if m else None


async def _async_insert(doc: dict) -> None:
    await get_db().messages.insert_one(doc)


def _run_insert_sync(doc: dict) -> None:
    """Run the Motor insert inside its own loop on a worker thread so the
    sync `send_message` wrapper can be called from any context."""
    container: dict = {}

    def _target() -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_async_insert(doc))
        except BaseException as exc:  # noqa: BLE001
            container["error"] = exc
        finally:
            loop.close()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join()
    if "error" in container:
        raise container["error"]


def send_message(caregiver_id: str, text: str, media_url: str | None = None) -> dict:
    """Log an outbound chat message to Mongo and return a stub payload.

    Returns the Phase-1 shape with a real `message_id` + `sent_at`:

        {message_id, caregiver_id, text, media_url, status, provider, sent_at}

    The sync signature is preserved intentionally: cross-feature callers
    (grading signoff, policy answer flow) can hit this from any context.
    Prefer `send_message_async` from the async code paths inside the
    channel feature itself.
    """
    message_id = uuid.uuid4().hex
    media_id = _extract_media_id(media_url)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": message_id,
        "caregiver_id": caregiver_id,
        "direction": "out",
        "channel": "web",
        "text": text,
        "media_id": media_id,
        "created_at": now,
    }
    # Prefer the running loop (we're probably inside a request handler).
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_async_insert(doc))
    except RuntimeError:
        _run_insert_sync(doc)
    return {
        "message_id": message_id,
        "caregiver_id": caregiver_id,
        "text": text,
        "media_url": media_url,
        "status": "sent",
        "provider": "web",
        "sent_at": now,
    }


async def send_message_async(
    caregiver_id: str,
    text: str,
    *,
    media_id: str | None = None,
) -> dict:
    """Async variant used by the channel's state machine. Returns the same
    public shape; writes synchronously (awaited) so the chat UI sees the
    message immediately on its next poll."""
    message_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "_id": message_id,
        "caregiver_id": caregiver_id,
        "direction": "out",
        "channel": "web",
        "text": text,
        "media_id": media_id,
        "created_at": now,
    }
    await get_db().messages.insert_one(doc)
    return {
        "message_id": message_id,
        "caregiver_id": caregiver_id,
        "text": text,
        "media_url": f"/api/media/{media_id}" if media_id else None,
        "status": "sent",
        "provider": "web",
        "sent_at": now,
    }
