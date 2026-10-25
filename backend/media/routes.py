"""HTTP routes for media upload/download.

`GET /{uuid}` supports HTTP byte-range requests (`Range: bytes=start-end`)
and emits `Accept-Ranges: bytes` + `Content-Length`. iPhone Safari and
most mobile browsers probe videos with `bytes=0-1` before pulling the
rest; without a `206` response they refuse to play.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from .store import get_media_store

# Content-type allowlist (spec).
ALLOWED_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "audio/mpeg",
    "audio/wav",
    "audio/webm",
    "image/jpeg",
    "image/png",
    "image/webp",
}

MAX_BYTES = 50 * 1024 * 1024  # 50 MB

router = APIRouter()

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


@router.post("")
@router.post("/")
async def upload_media(file: UploadFile = File(...)) -> dict:
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content-type: {content_type!r}",
        )

    # Enforce size cap while streaming to memory.
    buf = bytearray()
    chunk_size = 1024 * 1024
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {MAX_BYTES} bytes.",
            )

    store = get_media_store()
    uid = await store.save(bytes(buf), content_type, filename=file.filename)
    return {
        "uuid": uid,
        "url": f"/api/media/{uid}",
        "content_type": content_type,
        "size": len(buf),
    }


@router.get("/{uuid_str}")
async def get_media(uuid_str: str, request: Request):
    store = get_media_store()
    try:
        info = await store.open(uuid_str)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="media not found")

    length = info["length"]
    content_type = info["content_type"]
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": f'inline; filename="{info["filename"]}"',
    }

    range_header = request.headers.get("range") or request.headers.get("Range")
    if range_header:
        m = _RANGE_RE.match(range_header.strip())
        if m:
            start_s, end_s = m.group(1), m.group(2)
            if not start_s and not end_s:
                m = None
        if m:
            start_s, end_s = m.group(1), m.group(2)
            if start_s == "" and end_s != "":
                # "bytes=-N" → last N bytes
                suffix = int(end_s)
                if suffix <= 0:
                    return Response(status_code=416, headers={"Content-Range": f"bytes */{length}"})
                start = max(0, length - suffix)
                end = length - 1
            else:
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else length - 1
            if start >= length or end >= length or start > end:
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{length}"},
                )
            headers["Content-Range"] = f"bytes {start}-{end}/{length}"
            headers["Content-Length"] = str(end - start + 1)
            return StreamingResponse(
                store.read_range(info, start, end),
                status_code=206,
                media_type=content_type,
                headers=headers,
            )
        # Malformed Range header — fall through to full response.

    headers["Content-Length"] = str(length)
    return StreamingResponse(
        store.read_full(info),
        media_type=content_type,
        headers=headers,
    )
