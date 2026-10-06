"""Assemble the HTTP API: the health route and the read-only views of the law bundles."""

from importlib.metadata import version
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from influence.extraction.cli import default_data_root
from influence.routers import atlas, health, lineage

# Installed metadata makes pyproject.toml the single source for the API version.
VERSION = version("influence")
# The dev explorer's origins. Through Next.js's proxy the browser never calls the API
# directly, so this only matters for a page served elsewhere than the proxy.
LOCAL_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def create_app(atlas_data_root: Path | None = None) -> FastAPI:
    """Build an app that serves the law bundles under `atlas_data_root`.

    The root holds what `influence atlas` and `influence lineage` write; it defaults to
    `INFLUENCE_DATA_ROOT` or the repository's `data/`, as the commands do. Every route
    reads; nothing is written through HTTP.
    """
    app = FastAPI(title="Influence Atlas API", version=VERSION)
    app.add_middleware(CORSMiddleware, allow_origins=LOCAL_ORIGINS, allow_methods=("GET",))
    app.state.atlas_data_root = atlas_data_root or default_data_root()
    app.include_router(health.router)
    app.include_router(atlas.router)
    app.include_router(lineage.router)
    return app


app = create_app()
