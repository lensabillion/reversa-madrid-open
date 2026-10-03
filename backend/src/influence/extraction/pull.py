"""Fetch a source URL and keep the untouched response on disk, with its provenance.

The cache is keyed by hash and is not meant to be read by a person. This writes the same
bytes a second time under the source's own directory, with a provenance file beside them,
so a parser (and a reviewer) can find the exact response a row came from.
"""

from dataclasses import dataclass
from pathlib import Path

from influence.extraction.catalog import SourceSpec
from influence.extraction.fetching import CachedFetcher
from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import DataLayout, LayoutError


@dataclass(frozen=True)
class StoredResponse:
    """Where the bytes landed and how many there were; the caller reports both."""

    body_path: Path
    provenance_path: Path
    byte_count: int


def target_directory(layout: DataLayout, spec: SourceSpec, procedure_id: str | None) -> Path:
    """Global sources get one directory; per-law sources live under their procedure."""
    if spec.scope == "global":
        return layout.global_source(spec.source_id)
    if procedure_id is None:
        raise LayoutError(f"Source {spec.letter} is {spec.scope}, so it needs a procedure id")
    return layout.law_source(procedure_id, spec.source_id)


def store_raw(
    layout: DataLayout,
    spec: SourceSpec,
    fetcher: CachedFetcher,
    url: str,
    *,
    name: str,
    procedure_id: str | None = None,
    refresh: bool = False,
) -> StoredResponse:
    """Fetch through the cache, then write the body and its provenance under `name`."""
    if not name or "/" in name or "\\" in name:
        raise LayoutError(f"Unusable raw file name {name!r}")
    response = fetcher.get(url, refresh=refresh)
    directory = target_directory(layout, spec, procedure_id)
    body_path = directory / name
    provenance_path = directory / f"{name}.provenance.json"
    write_bytes_atomic(body_path, response.body)
    write_bytes_atomic(provenance_path, response.metadata.model_dump_json(indent=2).encode("utf-8"))
    return StoredResponse(body_path, provenance_path, response.metadata.byte_count)
