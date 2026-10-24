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


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    mongo_client.close()


@app.get("/api/")
async def root():
    return {"service": "firstshift", "phase": 1, "status": "ok"}
