"""Synthetic seed for FirstShift Phase 2.

Idempotent: wipes the collections it owns and re-inserts.
Leaves `questions`, `cards`, `incidents`, `plans` untouched (reserved).

Runnable from the repo root:

    python -m backend.seed.seed

Also invoked automatically from `backend/server.py` on startup when
the `agencies` collection is empty.
"""
