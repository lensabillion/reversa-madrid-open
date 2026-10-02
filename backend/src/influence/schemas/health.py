"""Stable health response contract."""

from typing import Literal

from pydantic import BaseModel


class Health(BaseModel):
    """Liveness response; version identifies the installed build."""

    status: Literal["ok"]
    version: str
