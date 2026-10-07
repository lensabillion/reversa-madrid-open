"""Where extracted data lives, so adding a law never touches another law's files.

Global sources are fetched once; per-law sources live under the procedure's slug.
"""

import re
from dataclasses import dataclass
from pathlib import Path

# The catalog's source ids for global sources, plus the probe report's own directory.
GLOBAL_SOURCES = frozenset({"registry", "meetings_ec", "meetings_mep", "ep_opendata", "probe"})

# A procedure id such as 2021/0106(COD) contains characters that are path separators on
# POSIX and forbidden on Windows, so the directory name is a slug, never the raw id.
_NON_ALPHANUMERIC = re.compile(r"[^A-Za-z0-9]+")


class LayoutError(ValueError):
    """An identifier or source name cannot be turned into a path."""


def procedure_slug(procedure_id: str) -> str:
    """Map `2021/0106(COD)` to `2021-0106-COD`; reject ids with nothing to keep."""
    slug = _NON_ALPHANUMERIC.sub("-", procedure_id).strip("-")
    if not slug:
        raise LayoutError(f"Procedure id has no usable characters: {procedure_id!r}")
    return slug


@dataclass(frozen=True)
class DataLayout:
    """Paths under one data root. Creating a directory is explicit, never a side effect."""

    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    def global_source(self, name: str) -> Path:
        if name not in GLOBAL_SOURCES:
            raise LayoutError(f"Unknown global source {name!r}")
        return self.raw / name

    def law(self, procedure_id: str) -> Path:
        return self.raw / "laws" / procedure_slug(procedure_id)

    def law_source(self, procedure_id: str, name: str) -> Path:
        if not name or "/" in name or "\\" in name:
            raise LayoutError(f"Unusable per-law source name {name!r}")
        return self.law(procedure_id) / name
