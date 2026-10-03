"""Part 1 · Collect, once per machine: fetch the global files every law's run reads.

`influence collect` reads four Parltrack dumps and the Transparency Register export, and
the Have Your Say index when it exists, at the paths `CollectInputs.under` names. This
puts each one there, so a fresh checkout reaches its first law with two commands.

A dump or the export is streamed to disk through the fetching layer (declared identity,
rate limit) and published atomically: an interrupted or failed run leaves the previous
file, or none, never a truncated file that collect would trust. Beside each downloaded
file goes its `SourceDocument` (`<name>.source.json`): URL, retrieval time and SHA-256,
the record collect itself writes for a dump. The index is built by `hys.crawl_index`,
whose responses are cached, so an interrupted crawl resumes where it stopped.

A file already present is kept unless `refresh` is asked, so a rerun after a failure
fetches only what is missing. Collect keys its `amendments` stage by the hashes of three
dumps and its `asks` stage by those of the export and the index, so refreshing one of
those redoes the stage that reads it. The dossiers dump is in no stage key: a refreshed
one rebuilds the procedure catalog, but a law's saved stages are reused.
"""

from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from influence.extraction.cache import ResponseMetadata
from influence.extraction.fetching import CachedFetcher, FetchError
from influence.extraction.files import write_bytes_atomic
from influence.repositories import hys, parltrack
from influence.schemas.atlas import SourceDocument, document_id
from influence.services.collect import CollectInputs, file_sha256

type SetupGroup = Literal["parltrack", "register", "hys"]
type SetupAction = Literal["fetched", "built", "kept"]
type Describe = Callable[[Path, ResponseMetadata], SourceDocument]

# Run order: the required files first, so stopping the long index crawl loses nothing.
GROUPS: tuple[SetupGroup, ...] = ("parltrack", "register", "hys")
# The daily full export; transparency-register.europa.eu/odplastorganisationxml_en
# redirects here (docs/research/influence-atlas-2026-10/data-sources.md, section 2).
REGISTER_EXPORT_URL = (
    "https://ec.europa.eu/transparencyregister/public/files/ODP/download/XML/latest"
)
SOURCE_RECORD_SUFFIX = ".source.json"


class SetupError(RuntimeError):
    """A requested file could not be fetched or built. Files finished before it stay."""


@dataclass(frozen=True)
class SetupFile:
    """One file as this run left it: fetched now, built now, or kept from before."""

    path: Path
    byte_count: int
    sha256: str
    action: SetupAction


def source_record_path(path: Path) -> Path:
    return path.with_name(f"{path.name}{SOURCE_RECORD_SUFFIX}")


def setup_data(
    data_root: Path,
    *,
    groups: Collection[SetupGroup],
    fetcher: CachedFetcher,
    refresh: bool = False,
    progress: hys.Progress | None = None,
) -> Iterator[SetupFile]:
    """Yield each requested file once it is in place, in `GROUPS` order.

    A generator, so a caller can report the files finished before a `SetupError` stops
    the run. Files are handled one at a time and the first failure stops the run: a
    host that is down would otherwise cost a timeout per remaining request.
    """
    inputs = CollectInputs.under(data_root)
    if "parltrack" in groups:
        dumps = (inputs.dossiers, inputs.committee_amendments, inputs.plenary_amendments)
        for path in (*dumps, inputs.meps):
            url = f"{parltrack.DUMP_BASE_URL}{path.name}"
            yield _download(fetcher, url, path, _dump_record, refresh=refresh)
    if "register" in groups:
        yield _download(
            fetcher, REGISTER_EXPORT_URL, inputs.register, _export_record, refresh=refresh
        )
    if "hys" in groups:
        yield _index(fetcher, inputs.hys_index, refresh=refresh, progress=progress)


def _kept(path: Path) -> SetupFile:
    return SetupFile(path, path.stat().st_size, file_sha256(path), "kept")


def _download(
    fetcher: CachedFetcher, url: str, path: Path, describe: Describe, *, refresh: bool
) -> SetupFile:
    if path.is_file() and not refresh:
        return _kept(path)
    try:
        response = fetcher.download(url, path)
    except FetchError as error:
        raise SetupError(f"{path.name} was not downloaded and is unchanged: {error}") from error
    record = describe(path, response)
    write_bytes_atomic(source_record_path(path), record.model_dump_json(indent=2).encode("utf-8"))
    return SetupFile(path, response.byte_count, record.sha256, "fetched")


def _dump_record(path: Path, response: ResponseMetadata) -> SourceDocument:
    """The record collect writes for this dump, so the two never disagree on its fields."""
    return parltrack.dump_source_document(path, response.fetched_at)


def _export_record(path: Path, response: ResponseMetadata) -> SourceDocument:
    return SourceDocument(
        document_id=document_id("register", path.name),
        procedure_id=None,
        source_kind="register",
        url=response.url,
        title="EU Transparency Register export",
        # The export states its `exportDate` without a time zone, so it is not guessed.
        published_at=None,
        retrieved_at=response.fetched_at,
        sha256=file_sha256(path),
        media_type=response.content_type,
        extraction_status="not_applicable",
    )


def _index(
    fetcher: CachedFetcher, path: Path, *, refresh: bool, progress: hys.Progress | None
) -> SetupFile:
    """Crawl every initiative and write the index only when no initiative failed.

    A partial index would make collect report "no feedback" for a law whose initiative
    was skipped, so a failure writes nothing. Every response already received is cached,
    so a first build that stopped resumes on the next run. A refresh that stopped asks
    for every page again when rerun: it cannot tell a fresh entry from a stale one.
    """
    if path.is_file() and not refresh:
        return _kept(path)
    try:
        entries = list(hys.crawl_index(fetcher, refresh=refresh, progress=progress))
    except hys.HysError as error:
        raise SetupError(
            f"{path.name} was not built and is unchanged: {error}. Every response received "
            "so far is cached; a crawl without refresh reads them instead of asking again"
        ) from error
    hys.write_index(path, entries)
    return SetupFile(path, path.stat().st_size, file_sha256(path), "built")
