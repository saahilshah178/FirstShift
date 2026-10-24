"""HTTP routes for media upload/download."""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

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


@router.post("")
@router.post("/")
async def upload_media(request: Request, file: UploadFile = File(...)) -> dict:
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
    base = str(request.base_url).rstrip("/")
    return {
        "uuid": uid,
        "url": f"{base}/api/media/{uid}",
        "content_type": content_type,
        "size": len(buf),
    }


@router.get("/{uuid_str}")
async def get_media(uuid_str: str):
    store = get_media_store()
    try:
        stream, content_type, filename = await store.get(uuid_str)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="media not found")
    headers = {"Content-Disposition": f'inline; filename="{filename}"'}
    return StreamingResponse(stream, media_type=content_type, headers=headers)
