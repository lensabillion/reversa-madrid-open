"""Assemble the HTTP API while keeping dataset loading scoped to each app instance."""

import logging
import os
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import influence
from influence.extraction.cache import HttpCache
from influence.extraction.cli import default_data_root
from influence.extraction.fetching import CachedFetcher, UrllibFetcher
from influence.repositories.lobbyplag import (
    DatasetInvalidError,
    DatasetUnavailableError,
    DemoRepository,
    EntityNotFoundError,
)
from influence.routers import (
    atlas,
    comparison,
    demo,
    documents,
    health,
    laws,
    lineage,
    scoring,
)
from influence.services.collect import source_revision
from influence.services.demo import DemoService
from influence.services.law_search import LawService

# Installed metadata makes pyproject.toml the single source for the API version.
VERSION = version("influence")
LOCAL_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")
LOGGER = logging.getLogger(__name__)


def create_app(data_dir: Path | None = None, atlas_data_root: Path | None = None) -> FastAPI:
    """Build an app whose dataset is loaded once, on its first data request.

    `atlas_data_root` holds the law bundles `influence atlas` and `influence lineage` write;
    it defaults to `INFLUENCE_DATA_ROOT` or the repository's `data/`, as the commands do.
    """
    app = FastAPI(title="Influence Graph API", version=VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=LOCAL_ORIGINS,
        allow_methods=("GET", "POST"),
        allow_headers=("Content-Type",),
    )
    source_dir = data_dir or Path(
        os.environ.get(
            "INFLUENCE_DATA_DIR",
            Path(__file__).resolve().parents[3] / "data" / "lobbyplag",
        )
    )
    lock = Lock()
    service: DemoService | None = None

    def demo_service() -> DemoService:
        nonlocal service
        with lock:
            if service is None:
                service = DemoService(DemoRepository.load(source_dir))
            return service

    app.state.demo_service_provider = demo_service
    root = atlas_data_root or default_data_root()
    app.state.atlas_data_root = root
    app.state.law_service = LawService(
        root,
        fetcher=CachedFetcher(cache=HttpCache(root / "cache"), fetcher=UrllibFetcher()),
        code_revision=source_revision(Path(influence.__file__).parent),
        clock=lambda: datetime.now(UTC),
    )
    app.include_router(health.router)
    app.include_router(demo.router)
    app.include_router(scoring.router)
    app.include_router(documents.router)
    app.include_router(comparison.router)
    app.include_router(atlas.router)
    app.include_router(lineage.router)
    app.include_router(laws.router)

    @app.exception_handler(DatasetUnavailableError)
    async def unavailable(_request: Request, _error: DatasetUnavailableError) -> JSONResponse:
        LOGGER.error("Demo dataset unavailable", exc_info=_error)
        return JSONResponse(
            status_code=503,
            content={"detail": {"code": "dataset_unavailable", "message": "Dataset unavailable"}},
        )

    @app.exception_handler(DatasetInvalidError)
    async def invalid(_request: Request, _error: DatasetInvalidError) -> JSONResponse:
        LOGGER.error("Demo dataset invalid", exc_info=_error)
        return JSONResponse(
            status_code=503,
            content={"detail": {"code": "dataset_invalid", "message": "Dataset invalid"}},
        )

    @app.exception_handler(EntityNotFoundError)
    async def missing(_request: Request, _error: EntityNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": {"code": "entity_not_found", "message": "Entity not found"}},
        )

    return app


app = create_app()
