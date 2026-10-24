"""Lessons service — now backed by the real feature pipeline.

The signature stays sync (`build_lesson(video_id: str) -> dict`) as pinned
by `docs/CONTRACTS.md §3`. Internally we run the async pipeline on a
dedicated event loop so this function remains callable from any sync
context without changing other lanes.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone


def build_lesson(video_id: str) -> dict:
    """Build a lesson payload from a reference video (sync wrapper).

    Returns (unchanged shape from CONTRACTS.md §3):
        {
          "video_id": str,
          "title": str,
          "steps": [{"n","title","instruction","start","end","frame_id"}],
          "checks": [{"id","description","safety_critical"}],
          "quiz": [{"id","prompt","choices","answer_index"}],
          "translations": {"es": {...}, "tl": {...}},
          "model": str,
        }

    Internally runs the async feature pipeline on a dedicated thread's event
    loop so forks that invoke the stub from a request handler don't collide
    with the server's running loop.
    """
    container: dict = {}

    def _runner() -> None:
        async def _async_build() -> dict:
            # Imported inside the thread so Motor binds a client to this loop.
            from ai.gemini import GEMINI_MODEL
            from features.lessons.transcode import ffprobe
            from features.lessons.pipeline import stage_analyze, stage_extract_frames

            # Fetch original bytes to probe duration (we only have a video_id).
            # The pipeline operates on video_id directly after that.
            from media.store import get_media_store

            store = get_media_store()
            stream, _ct, _fn = await store.get(video_id)
            import os as _os
            import tempfile as _tempfile
            import uuid as _uuid
            tmp = _os.path.join(_tempfile.gettempdir(), f"stub-src-{_uuid.uuid4().hex}.mp4")
            try:
                with open(tmp, "wb") as f:
                    async for chunk in stream:
                        f.write(chunk)
                probe = await ffprobe(tmp)
            finally:
                try:
                    _os.remove(tmp)
                except Exception:  # noqa: BLE001
                    pass
            duration_s = probe.duration_s or 0.0

            draft, _problems = await stage_analyze(video_id, duration_s)
            with_frames = await stage_extract_frames(video_id, draft)

            # Translations placeholders — this stub does not publish, so return
            # stale markers. (Translation runs at publish, per the spec.)
            translations = {
                "es": {"status": "stale"},
                "tl": {"status": "stale"},
            }

            return {
                "video_id": video_id,
                "title": with_frames.get("title") or "",
                "steps": with_frames.get("steps") or [],
                "checks": with_frames.get("checks") or [],
                "quiz": with_frames.get("quiz") or [],
                "translations": translations,
                "model": GEMINI_MODEL,
            }

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            container["result"] = loop.run_until_complete(_async_build())
        except BaseException as exc:  # noqa: BLE001
            container["error"] = exc
        finally:
            loop.close()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if "error" in container:
        raise container["error"]
    return container["result"]
