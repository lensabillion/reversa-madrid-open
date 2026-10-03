"""The per-law manifest: one identifier in, every derived identifier and source out.

A law enters the pipeline as a procedure id. This module holds what resolving it
produces, so no downstream step ever carries a hardcoded CELEX number or document URL.
The `available` block is the fail-soft switch: a law with no public consultation still
produces a graph from amendments alone, and the report can say what was missing.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from influence.extraction.files import write_bytes_atomic


class ManifestError(ValueError):
    """A manifest is absent, unreadable, or does not match the contract."""


class DocumentReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    type: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str | None = None


class SourceAvailability(BaseModel):
    """Absent means checked and not there, not unchecked: every field defaults to False."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    oeil: bool = False
    eurlex_proposal: bool = False
    eurlex_final: bool = False
    hys: bool = False
    amendments: bool = False

    def missing(self) -> tuple[str, ...]:
        """Name the absent sources, which the per-law coverage report shows to the jury."""
        return tuple(name for name, present in self.model_dump().items() if not present)


class LawManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    procedure_id: str = Field(min_length=1)
    title: str | None = None
    celex_proposal: str | None = None
    celex_final: str | None = None
    lead_committee: str | None = None
    rapporteurs: tuple[str, ...] = ()
    # The numeric id ending every Have Your Say initiative URL; resolved per law.
    hys_publication_id: int | None = None
    documents: tuple[DocumentReference, ...] = ()
    available: SourceAvailability = SourceAvailability()
    resolved_at: datetime | None = None


def write_manifest(path: Path, manifest: LawManifest) -> None:
    write_bytes_atomic(path, manifest.model_dump_json(indent=2).encode("utf-8"))


def read_manifest(path: Path) -> LawManifest:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ManifestError(f"Cannot read manifest at {path}") from error
    try:
        return LawManifest.model_validate_json(content)
    except ValidationError as error:
        raise ManifestError(f"Manifest at {path} is invalid: {error}") from error
