"""Feature packages for FirstShift.

Each subpackage is auto-discovered at startup by `backend/server.py`.
A valid feature package exposes a module-level `router: fastapi.APIRouter`
in its `__init__.py`. The server mounts it at `/api/<package_name>`.
"""
