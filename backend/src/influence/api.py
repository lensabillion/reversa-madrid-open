"""
HTTP API that the Next.js frontend calls.

`create_app` builds a new application on each call, so a test can construct its own
instance; `app` is the instance uvicorn serves (`uvicorn influence.api:app`).
"""

from importlib.metadata import version
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

# Installed metadata, so `[project].version` in pyproject.toml is the only source. Raises
# PackageNotFoundError at import if the package is not installed, rather than guessing.
VERSION = version("influence")


class Health(BaseModel):
    """
    Liveness response. `version` lets a caller confirm which build answered.
    """

    status: Literal["ok"]
    version: str


def create_app() -> FastAPI:
    app = FastAPI(title="Influence Graph API", version=VERSION)

    @app.get("/health")
    def health() -> Health:
        return Health(status="ok", version=VERSION)

    return app


app = create_app()
