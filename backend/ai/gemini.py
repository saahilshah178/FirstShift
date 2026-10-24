"""Gemini helper + health endpoint.

- `call_gemini(prompt, media_uuids, response_schema, fps)` is the one entry
  point other modules (and later feature branches) should use.
- Small media is sent inline. Videos > 20 MB are uploaded via the File API
  and polled until ACTIVE before the generate call.
- `GET /api/ai/health` generates a tiny PNG at startup, sends it to Gemini,
  and verifies structured output round-trips. Returns 503 when
  `GEMINI_API_KEY` is missing or the call fails.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from media.store import get_media_store

logger = logging.getLogger("firstshift.ai")

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
VIDEO_INLINE_THRESHOLD = 20 * 1024 * 1024  # 20 MB → use File API above this
FILE_API_POLL_TIMEOUT_S = 60
FILE_API_POLL_INTERVAL_S = 1.5


def _get_client():
    """Build a google-genai client bound to GEMINI_API_KEY.

    Raises RuntimeError when the key is missing — callers should catch and
    return a 503 (never crash the app).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    # Import here so the app can still start even if `google-genai` fails
    # to import at module load time (unlikely, but keeps the backbone robust).
    from google import genai  # type: ignore

    return genai.Client(api_key=api_key)


async def _read_all(uuid_str: str) -> tuple[bytes, str, str]:
    """Pull a GridFS blob fully into memory. Returns (bytes, mime, filename)."""
    store = get_media_store()
    stream, content_type, filename = await store.get(uuid_str)
    buf = bytearray()
    async for chunk in stream:
        buf.extend(chunk)
    return bytes(buf), content_type, filename


def _is_video(mime: str) -> bool:
    return mime.startswith("video/")


async def _upload_via_file_api(client, data: bytes, mime: str, filename: str):
    """Upload bytes via Gemini File API, poll until ACTIVE, return the File."""
    from google.genai import types  # type: ignore

    # SDK calls are blocking → run in a thread.
    def _upload():
        return client.files.upload(
            file=io.BytesIO(data),
            config=types.UploadFileConfig(
                mime_type=mime, display_name=filename
            ),
        )

    uploaded = await asyncio.to_thread(_upload)

    deadline = asyncio.get_event_loop().time() + FILE_API_POLL_TIMEOUT_S
    while True:
        state = getattr(uploaded.state, "name", str(uploaded.state))
        if state == "ACTIVE":
            return uploaded
        if state == "FAILED":
            raise RuntimeError(f"Gemini file upload FAILED: {uploaded.name}")
        if asyncio.get_event_loop().time() > deadline:
            raise TimeoutError(
                f"Gemini file {uploaded.name} did not reach ACTIVE in "
                f"{FILE_API_POLL_TIMEOUT_S}s (state={state})"
            )
        await asyncio.sleep(FILE_API_POLL_INTERVAL_S)
        uploaded = await asyncio.to_thread(client.files.get, name=uploaded.name)


async def _build_part(client, uuid_str: str):
    """Build a Content part for a given media UUID (inline or File-API ref)."""
    from google.genai import types  # type: ignore

    data, mime, filename = await _read_all(uuid_str)
    if _is_video(mime) and len(data) > VIDEO_INLINE_THRESHOLD:
        uploaded = await _upload_via_file_api(client, data, mime, filename)
        return types.Part.from_uri(file_uri=uploaded.uri, mime_type=mime)
    return types.Part.from_bytes(data=data, mime_type=mime)


async def call_gemini(
    prompt: str,
    media_uuids: list[str] | None = None,
    response_schema: dict | None = None,
    fps: int | None = None,
) -> dict:
    """Call Gemini with text + optional media + optional structured output.

    Args:
        prompt: text prompt.
        media_uuids: UUIDs returned by `/api/media`.
        response_schema: when provided, Gemini is asked for structured JSON
            matching this schema; the function parses the JSON response and
            returns it as a dict.
        fps: optional video frame sampling rate (reserved; passed through
            when the SDK supports it on video parts).

    Returns:
        - When `response_schema` is set: the parsed JSON dict.
        - Otherwise: `{"text": <raw text>}`.
    """
    from google.genai import types  # type: ignore

    client = _get_client()
    media_uuids = media_uuids or []

    parts: list[Any] = [types.Part.from_text(text=prompt)]
    for uid in media_uuids:
        parts.append(await _build_part(client, uid))

    config_kwargs: dict[str, Any] = {}
    if response_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = response_schema

    config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

    def _call():
        return client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=parts)],
            config=config,
        )

    # Retry on 503 UNAVAILABLE: 1s then 3s backoff (max 2 retries).
    from google.genai.errors import ServerError  # type: ignore

    delays = [1.0, 3.0]
    attempt = 0
    while True:
        try:
            response = await asyncio.to_thread(_call)
            break
        except ServerError as exc:
            code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if code == 503 and attempt < len(delays):
                logger.warning(
                    "Gemini 503 UNAVAILABLE (attempt %d); retrying in %.1fs",
                    attempt + 1,
                    delays[attempt],
                )
                await asyncio.sleep(delays[attempt])
                attempt += 1
                continue
            raise
    text = response.text or ""

    if response_schema is not None:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Gemini returned non-JSON despite response_schema: {text!r}"
            ) from exc
    return {"text": text}


# ---- Health endpoint ----
router = APIRouter()


def _tiny_test_png() -> bytes:
    """Generate a 16x16 solid teal PNG in memory (no bundled asset needed)."""
    from PIL import Image  # type: ignore

    img = Image.new("RGB", (16, 16), color=(0, 150, 136))  # teal
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


_HEALTH_SCHEMA = {
    "type": "object",
    "properties": {"color": {"type": "string"}},
    "required": ["color"],
}


@router.get("/health")
async def ai_health():
    if not os.environ.get("GEMINI_API_KEY"):
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "GEMINI_API_KEY is not set"},
        )
    try:
        # Save the tiny PNG into GridFS so we exercise the same code path
        # (`_build_part`) as real usage.
        png = _tiny_test_png()
        store = get_media_store()
        uid = await store.save(png, "image/png", filename="healthcheck.png")

        result = await call_gemini(
            prompt=(
                "Return JSON with a 'color' field describing the dominant "
                "color in this image. Use a single English word."
            ),
            media_uuids=[uid],
            response_schema=_HEALTH_SCHEMA,
        )
        return {"ok": True, "model": GEMINI_MODEL, "result": result}
    except Exception as exc:  # noqa: BLE001 — surface error to caller
        logger.exception("ai_health failed")
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": str(exc)},
        )
