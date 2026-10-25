"""Role-based gating for FirstShift agency endpoints.

**NOT real auth.** The client sets `X-Firstshift-Role` from a localStorage
value; a motivated user can forge it by typing one header. This file is
the server-side half of the hide-and-disable UX that keeps non-Care
Manager roles out of destructive flows until real auth replaces it.

See `docs/CONTRACTS.md` §10 TODOs ("Role-switch and `/c/{code}` are not
real auth") and `docs/merge/mvp-hardening.md` → Role matrix for the full
endpoint × role table.

Usage:

    from roles import require_role, Role

    @router.post("/attempts/{attempt_id}/signoff")
    async def post_signoff(
        attempt_id: str,
        body: SignoffBody,
        _role: str = Depends(require_role({Role.CARE_MANAGER})),
    ):
        ...

- Missing `X-Firstshift-Role` header → `403 role_required`.
- Header present but role not in allow-set → `403 role_not_allowed`.
- Agency routes only. Caregiver endpoints (`/caregivers/by-code/{code}`,
  `/channel/inbound`, `/questions/ask`, etc.) MUST NOT be gated — the
  caregiver side is role-independent (Batch-3 decision).
"""
from __future__ import annotations

from typing import Iterable

from fastapi import Depends, Header, HTTPException


class Role:
    """String constants so endpoint declarations read like English."""
    CARE_MANAGER = "Care Manager"
    TRAINER = "Trainer"
    SCHEDULER = "Scheduler"


AGENCY_ROLES: frozenset[str] = frozenset({Role.CARE_MANAGER, Role.TRAINER, Role.SCHEDULER})


def require_role(allowed: Iterable[str]):
    """Return a FastAPI dependency that checks `X-Firstshift-Role`.

    The returned dependency raises `403` with a stable `detail` shape:

        {"reason": "role_required", "allowed": [<role>, ...]}
        {"reason": "role_not_allowed", "role": <role>, "allowed": [<role>, ...]}

    The frontend 403 toast reads `detail.allowed` to compose a friendly
    message; keep this shape pinned.
    """
    allowed_set = frozenset(allowed)
    allowed_sorted = sorted(allowed_set)

    async def _dep(
        x_firstshift_role: str | None = Header(default=None),
    ) -> str:
        role = (x_firstshift_role or "").strip()
        if not role:
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "role_required",
                    "allowed": allowed_sorted,
                },
            )
        if role not in allowed_set:
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "role_not_allowed",
                    "role": role,
                    "allowed": allowed_sorted,
                },
            )
        return role

    return _dep


__all__ = ["Role", "AGENCY_ROLES", "require_role"]
