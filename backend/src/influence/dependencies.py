"""Dependencies shared by the demo routes."""

from collections.abc import Callable
from typing import cast

from fastapi import Request

from influence.services.demo import DemoService


def get_demo_service(request: Request) -> DemoService:
    """Resolve the provider attached to the current app for FastAPI injection."""
    provider = cast("Callable[[], DemoService]", request.app.state.demo_service_provider)
    return provider()
