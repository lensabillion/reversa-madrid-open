"""Public data root and path-safe law identifiers."""

import os
import re
from pathlib import Path

_NON_ALPHANUMERIC = re.compile(r"[^A-Za-z0-9]+")


class LayoutError(ValueError):
    """An identifier or source name cannot be turned into a path."""


def procedure_slug(procedure_id: str) -> str:
    """Map `2021/0106(COD)` to `2021-0106-COD`; reject ids with nothing to keep."""
    slug = _NON_ALPHANUMERIC.sub("-", procedure_id).strip("-")
    if not slug:
        raise LayoutError(f"Procedure id has no usable characters: {procedure_id!r}")
    return slug


def default_data_root() -> Path:
    """`INFLUENCE_DATA_ROOT`, or the repository's `data/` beside the installed source."""
    override = os.environ.get("INFLUENCE_DATA_ROOT")
    if override is not None:
        return Path(override)
    return Path(__file__).resolve().parents[4] / "data"
