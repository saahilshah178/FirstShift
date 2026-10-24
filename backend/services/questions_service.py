"""Questions service — swapped from the Phase-1 stub.

Signature preserved exactly:

    answer_question(caregiver_id: str, text: str) -> dict

Internally dispatches to the async pipeline on a worker-thread event loop so
cross-feature sync callers can hit it without colliding with the server's
running loop. In practice the FastAPI handler for `POST /api/channel/inbound`
calls `answer_question_async` directly; this sync wrapper exists for CLI /
test harnesses and backwards-compat with the Phase-1 shape.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone


def answer_question(caregiver_id: str, text: str) -> dict:
    """Answer a free-form caregiver question via Gemini + policies + cards.

    Preserves the Phase-1 return shape:
        {question_id, caregiver_id, question, answer, citations,
         confidence, answered_at, model}
    """
    container: dict = {}

    def _target() -> None:
        from features.questions.pipeline import answer_question_async
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            container["result"] = loop.run_until_complete(
                answer_question_async(caregiver_id, text)
            )
        except BaseException as exc:  # noqa: BLE001
            container["error"] = exc
        finally:
            loop.close()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join()
    if "error" in container:
        raise container["error"]
    result = container["result"]
    # Backfill the Phase-1 fields in case something got dropped.
    result.setdefault("answered_at", datetime.now(timezone.utc).isoformat())
    result.setdefault("citations", [])
    result.setdefault("confidence", 0.0)
    result.setdefault("model", "gemini")
    return result
