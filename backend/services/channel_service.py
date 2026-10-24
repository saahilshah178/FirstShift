"""Channel service stub.

Returns a realistic send-message payload. In Phase 2+ this will push
the message out over Twilio/WhatsApp or a websocket channel.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def send_message(caregiver_id: str, text: str, media_url: str | None = None) -> dict:
    """Send an outbound message to a caregiver.

    Returns:
        {
          "message_id": str (uuid4 hex),
          "caregiver_id": str,
          "text": str,
          "media_url": str | None,
          "status": "queued"|"sent"|"failed",
          "provider": str,
          "sent_at": ISO-8601 str,
        }
    """
    return {
        "message_id": uuid.uuid4().hex,
        "caregiver_id": caregiver_id,
        "text": text,
        "media_url": media_url,
        "status": "queued",
        "provider": "stub",
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
