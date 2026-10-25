"""Backend one-shot scripts (migrations, backfills, dedups).

Each module is runnable via `python -m backend.scripts.<name>` from the
repo root OR directly from `/app/backend` as `python -m scripts.<name>`.
All scripts are expected to be idempotent — a second run must be a no-op
on an already-migrated database.
"""
