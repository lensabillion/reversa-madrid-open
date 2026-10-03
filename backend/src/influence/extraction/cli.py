"""The extraction command line: list the catalog, probe it, fetch a source URL raw.

Nothing here parses a response. Parsers are written after `probe` shows what a source
actually returns, which is the order the playbook requires and the reason the morning
starts with this command rather than with code.
"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from influence.extraction import catalog, probe, pull
from influence.extraction.cache import CacheError, HttpCache
from influence.extraction.catalog import Scope, UnknownSourceError
from influence.extraction.fetching import CachedFetcher, FetchError
from influence.extraction.layout import DataLayout, LayoutError

SCOPES: tuple[Scope, ...] = ("global", "per_law", "enrichment")


def default_data_root() -> Path:
    """`INFLUENCE_DATA_ROOT`, or the repository's `data/` beside the installed source."""
    override = os.environ.get("INFLUENCE_DATA_ROOT")
    if override is not None:
        return Path(override)
    return Path(__file__).resolve().parents[4] / "data"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="influence-extract", description=__doc__)
    parser.add_argument(
        "--data-root", type=Path, default=None, help="Overrides INFLUENCE_DATA_ROOT"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    sources = subcommands.add_parser("sources", help="List the source catalog")
    sources.add_argument("--scope", choices=SCOPES, default=None)

    probing = subcommands.add_parser("probe", help="Fetch each base URL and record what it returns")
    probing.add_argument("--scope", choices=SCOPES, default=None)
    probing.add_argument("--refresh", action="store_true", help="Ignore cached responses")

    fetch = subcommands.add_parser("fetch", help="Fetch one URL and store it raw with provenance")
    fetch.add_argument("source", help="Catalog letter (A) or id (registry)")
    fetch.add_argument("url")
    fetch.add_argument("--name", required=True, help="File name under the source's directory")
    fetch.add_argument("--law", default=None, help="Procedure id, required for per-law sources")
    fetch.add_argument("--refresh", action="store_true", help="Ignore cached responses")
    return parser


def _specs(scope: Scope | None) -> tuple[catalog.SourceSpec, ...]:
    return catalog.SOURCES if scope is None else catalog.by_scope(scope)


def _fetcher(root: Path) -> CachedFetcher:
    return CachedFetcher(cache=HttpCache(DataLayout(root).cache))


def _run_sources(scope: Scope | None, out: TextIO) -> int:
    for spec in _specs(scope):
        url = spec.probe_url or "no base URL"
        print(f"{spec.letter} {spec.source_id} [{spec.scope}/{spec.verification}] {url}", file=out)
    return 0


def _run_probe(root: Path, scope: Scope | None, *, refresh: bool, out: TextIO) -> int:
    """Exit non-zero when any source is unreachable: the probe is a gate, not a listing."""
    layout = DataLayout(root)
    report = probe.probe_sources(_fetcher(root), _specs(scope), refresh=refresh)
    path = layout.global_source("probe") / "probe-report.json"
    probe.write_report(path, report)
    print(probe.format_report(report), file=out)
    print(f"Report written to {path}", file=out)
    return 1 if report.unreachable() else 0


def _run_fetch(root: Path, arguments: argparse.Namespace, out: TextIO) -> int:
    spec = catalog.source(str(arguments.source))
    stored = pull.store_raw(
        DataLayout(root),
        spec,
        _fetcher(root),
        str(arguments.url),
        name=str(arguments.name),
        procedure_id=arguments.law,
        refresh=bool(arguments.refresh),
    )
    print(f"{stored.byte_count} bytes to {stored.body_path}", file=out)
    print(f"Provenance to {stored.provenance_path}", file=out)
    return 0


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    """Return an exit code; every expected failure prints one line instead of a traceback."""
    stream = out if out is not None else sys.stdout
    arguments = build_parser().parse_args(argv)
    root = arguments.data_root if arguments.data_root is not None else default_data_root()
    try:
        if arguments.command == "sources":
            return _run_sources(arguments.scope, stream)
        if arguments.command == "probe":
            return _run_probe(root, arguments.scope, refresh=bool(arguments.refresh), out=stream)
        return _run_fetch(root, arguments, stream)
    except (FetchError, CacheError, LayoutError, UnknownSourceError) as error:
        print(f"error: {error}", file=stream)
        return 2
