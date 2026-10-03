"""Probe every documented base URL and record what it actually returns.

The playbook budgets the first fifteen minutes of the day to this, because no endpoint
in the catalog has been hit with a live request and a parser written against an imagined
response shape is worse than no parser. Probing is fail-soft by construction: a refusal
is a recorded result, not an exception that ends the run.
"""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from influence.extraction.catalog import SourceSpec, probeable
from influence.extraction.fetching import CachedFetcher, FetchError
from influence.extraction.files import write_bytes_atomic

# Enough to recognise XML, JSON, HTML or a redirect notice; never enough to be data.
SNIFF_CHARACTERS = 200


class ProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    letter: str
    source_id: str
    url: str
    verification: str
    reachable: bool
    status: int | None
    content_type: str | None
    byte_count: int | None = Field(default=None, ge=0)
    sniff: str | None
    error: str | None


class ProbeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    probed_at: datetime
    results: tuple[ProbeResult, ...]

    def unreachable(self) -> tuple[ProbeResult, ...]:
        return tuple(result for result in self.results if not result.reachable)


def _sniff(body: bytes) -> str:
    return body[: SNIFF_CHARACTERS * 4].decode("utf-8", errors="replace")[:SNIFF_CHARACTERS]


def probe_source(fetcher: CachedFetcher, spec: SourceSpec, *, refresh: bool = False) -> ProbeResult:
    """Fetch one base URL through the cache, turning any failure into a recorded result."""
    url = spec.probe_url
    if url is None:
        raise ValueError(f"Source {spec.letter} has no probe URL; filter with catalog.probeable")
    try:
        response = fetcher.get(url, refresh=refresh)
    except FetchError as error:
        return ProbeResult(
            letter=spec.letter,
            source_id=spec.source_id,
            url=url,
            verification=spec.verification,
            reachable=False,
            status=error.status,
            content_type=None,
            sniff=None,
            error=error.reason,
        )
    return ProbeResult(
        letter=spec.letter,
        source_id=spec.source_id,
        url=url,
        verification=spec.verification,
        reachable=True,
        status=response.metadata.status,
        content_type=response.metadata.content_type,
        byte_count=response.metadata.byte_count,
        sniff=_sniff(response.body),
        error=None,
    )


def probe_sources(
    fetcher: CachedFetcher, specs: Iterable[SourceSpec], *, refresh: bool = False
) -> ProbeReport:
    """Probe every source that has a base URL; sources without one are skipped, not failed."""
    results = tuple(probe_source(fetcher, spec, refresh=refresh) for spec in probeable(specs))
    return ProbeReport(probed_at=fetcher.clock(), results=results)


def write_report(path: Path, report: ProbeReport) -> None:
    write_bytes_atomic(path, report.model_dump_json(indent=2).encode("utf-8"))


def format_report(report: ProbeReport) -> str:
    """One line per source, so the morning probe is readable in a terminal."""
    lines = [f"Probed {len(report.results)} sources at {report.probed_at.isoformat()}"]
    for result in report.results:
        if result.reachable:
            detail = f"{result.status} {result.content_type or 'no content type'}"
            detail = f"{detail}, {result.byte_count} bytes"
        else:
            detail = f"unreachable: {result.error}"
        lines.append(f"{result.letter} {result.source_id} [{result.verification}] {detail}")
    return "\n".join(lines)
