"""channel feature.

Routes mounted at `/api/channel`:
- GET  `/`                                    placeholder marker (Phase-1 shape, preserved).
- GET  `/messages/{caregiver_id}`             full message thread.
- GET  `/conversation/{caregiver_id}`         current FSM state.
- POST `/inbound`                             drive the FSM with {caregiver_id, text?, media_id?}.
- POST `/inbound-video`                       multipart video → stores + drives the FSM.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter

from .routes import router as _inner_router

logger = logging.getLogger("firstshift.channel")

router = APIRouter()


@router.get("/")
async def placeholder() -> dict:
    return {"feature": "channel", "status": "placeholder"}


router.include_router(_inner_router)


# ---- startup side-effects ----
async def _startup_tasks() -> None:
    try:
        from seed.policies import seed_policies
        n = await seed_policies()
        if n:
            logger.info("channel: seeded %d policy row(s) at startup", n)
    except Exception:  # noqa: BLE001
        logger.exception("channel: startup policy seed failed")


try:
    asyncio.get_running_loop().create_task(_startup_tasks())
except RuntimeError:
    pass
