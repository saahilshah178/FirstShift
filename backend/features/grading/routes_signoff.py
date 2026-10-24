"""Stage-5 signoff + competency routes.

This module is populated in the next commit; for Stage 4 we expose a
no-op `attach(router)` so the feature imports cleanly without
registering any new endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter


def attach(router: APIRouter) -> None:
    """Register signoff / queue / per-caregiver competency routes.

    Stage 4: no-op. Stage 5 fills this in.
    """
    return None
