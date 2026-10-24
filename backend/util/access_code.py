"""Access-code generator for caregiver lookup.

Alphabet omits visually ambiguous chars: 0 / O, 1 / I / L. 6 chars.
Callers that insert into Mongo should wrap the generate + insert with
`retry_on_duplicate` so a rare collision does not surface as a 500.
"""
from __future__ import annotations

import secrets
from typing import Awaitable, Callable, TypeVar

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LENGTH = 6
MAX_RETRIES = 5

T = TypeVar("T")


def generate_access_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


async def retry_on_duplicate(
    insert_with_code: Callable[[str], Awaitable[T]],
    *,
    max_retries: int = MAX_RETRIES,
) -> T:
    """Call `insert_with_code(code)` with fresh codes until it succeeds.

    `insert_with_code` must raise `pymongo.errors.DuplicateKeyError` when
    the collision is on `access_code`. Anything else bubbles up.
    """
    from pymongo.errors import DuplicateKeyError  # local import keeps util light

    last_exc: Exception | None = None
    for _ in range(max_retries):
        code = generate_access_code()
        try:
            return await insert_with_code(code)
        except DuplicateKeyError as exc:  # noqa: PERF203
            last_exc = exc
            continue
    raise RuntimeError(
        f"could not allocate a unique access code after {max_retries} tries"
    ) from last_exc
