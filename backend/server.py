"""FirstShift backend — Phase 1 backbone.

- Auto-discovers feature packages under `backend/features/` at startup.
- Mounts each feature's `router` at `/api/<name>`.
- Mounts core (non-feature) routers: media, ai.
- Ensures MongoDB collections and indexes exist on startup.
"""
from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# Make the static ffmpeg + ffprobe at `/root/.local/bin` discoverable even
# when supervisor's `environment=` directive drops the user PATH. The pod
# does NOT ship with ffmpeg in `/usr/bin` across restarts (apt packages
# don't persist); the static binary at `/root/.local/bin` does.
_STATIC_FFMPEG_DIR = "/root/.local/bin"
if _STATIC_FFMPEG_DIR not in os.environ.get("PATH", "").split(":"):
    os.environ["PATH"] = f"{_STATIC_FFMPEG_DIR}:{os.environ.get('PATH', '')}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("firstshift")

# ---- Mongo ----
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "firstshift")
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client[DB_NAME]

# Collections used by Phase 1 (no documents inserted yet).
_COLLECTIONS = [
    "agencies",
    "caregivers",
    "clients",
    "skills",
    "attempts",
    "signoffs",
    "questions",
    "cards",
    "incidents",
    "plans",
]


async def _ensure_collections_and_indexes() -> None:
    existing = set(await db.list_collection_names())
    for name in _COLLECTIONS:
        if name not in existing:
            await db.create_collection(name)
            logger.info("created collection: %s", name)
    # Access-code uniqueness (used in Phase 2).
    await db.caregivers.create_index("access_code", unique=True, sparse=True)


# ---- App ----
app = FastAPI(
    title="FirstShift",
    version="0.1.0",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _discover_and_mount_features() -> list[str]:
    """Walk backend/features/*, import each subpackage, mount its `router`.

    - Each subpackage's `__init__.py` must expose a module-level
      `router: APIRouter`.
    - Mount path: `/api/<subpackage_name>`.
    - Import failures are logged and skipped (do not crash the app).
    """
    mounted: list[str] = []
    features_pkg = importlib.import_module("features")
    for mod_info in pkgutil.iter_modules(features_pkg.__path__):
        if not mod_info.ispkg:
            continue
        name = mod_info.name
        try:
            module = importlib.import_module(f"features.{name}")
            router = getattr(module, "router", None)
            if router is None:
                logger.warning("feature '%s' has no `router`; skipped", name)
                continue
            app.include_router(router, prefix=f"/api/{name}")
            mounted.append(name)
            logger.info("mounted feature: /api/%s", name)
        except Exception as exc:  # noqa: BLE001 — spec: log + skip
            logger.exception("failed to import feature '%s': %s", name, exc)
    return mounted


# Core (non-feature) routers.
from media.routes import router as media_router  # noqa: E402
from ai.gemini import router as ai_router  # noqa: E402

app.include_router(media_router, prefix="/api/media")
app.include_router(ai_router, prefix="/api/ai")


@app.on_event("startup")
async def _on_startup() -> None:
    await _ensure_collections_and_indexes()
    mounted = _discover_and_mount_features()
    logger.info("features mounted: %s", mounted)
    # Auto-seed when the agencies collection is empty.
    try:
        from seed.seed import seed_if_empty
        await seed_if_empty()
    except Exception as exc:  # noqa: BLE001 — never crash on seed failure
        logger.exception("auto-seed failed: %s", exc)
    # Stage 3 — integrity sweep + plans backfill + cert-map seed. All
    # idempotent; safe on every start.
    try:
        from features.plans.integrity import run_integrity_sweep
        from features.plans.seed import startup as plans_startup
        await run_integrity_sweep()
        await plans_startup()
    except Exception as exc:  # noqa: BLE001
        logger.exception("stage3 startup hooks failed: %s", exc)


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    mongo_client.close()


@app.get("/api/")
async def root():
    return {"service": "firstshift", "phase": 1, "status": "ok"}
