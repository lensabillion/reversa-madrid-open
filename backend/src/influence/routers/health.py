"""Liveness route: it reads no data."""

from importlib.metadata import version

from fastapi import APIRouter

from influence.schemas.health import Health

router = APIRouter()


@router.get("/health")
def health() -> Health:
    return Health(status="ok", version=version("influence"))
