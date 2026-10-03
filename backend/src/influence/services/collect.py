"""Collect one law: from what a person typed to its normalised public record on disk.

The connectors each know one source. This service joins them: it resolves the query to
one procedure (Parltrack catalog, then CELLAR), runs the stages below through the
`StageStore`, labels every gap, and publishes the run manifest last.

| Stage | Sources | Files |
| --- | --- | --- |
| `law_texts` | CELLAR | `documents`, `texts`, `articles` |
| `amendments` | Parltrack dumps | `documents`, `amendments` |
| `asks` | Have Your Say, Transparency Register | `documents`, `texts`, `passages`, `submitters` |
| `actors` | the two stages above, Parltrack Members | `actors` |
| `metadata` | everything above | `law` |

Every stage also writes `coverage.jsonl`, the coverage rows it is responsible for, so a
reused stage reports the same gaps with the same reasons as the run that produced it.

Two rules decide what stops a run. A required input stops it with a `CollectError`: the
query must resolve to exactly one procedure, and the law must have amendments or asks,
because with neither there is nothing to link. Everything else (a text CELLAR lacks, a
consultation the API does not serve, an attachment that will not download) is a coverage
row with a reason, and the run goes on. A stage that met a failure which may not repeat
(a request that failed, a file that was absent) is never reused: the next run tries again.

Nothing here reaches the network or the clock on its own: the fetcher, the clock and the
data root are parameters, so a test runs the whole pipeline offline and repeatably.
"""

import re
import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import get_args

from pydantic import ValidationError

from influence.extraction.fetching import CachedFetcher
from influence.extraction.layout import procedure_slug
from influence.extraction.records import StageStore, input_hash
from influence.repositories import cellar, hys, parltrack
from influence.repositories.register import RegisterEntry, RegisterError, iter_register
from influence.schemas.atlas import (
    Actor,
    Amendment,
    ArticleStage,
    ArticleVersion,
    AtlasRecord,
    DocumentText,
    LawRecord,
    Layer,
    LayerCoverage,
    LayerStatus,
    Passage,
    RunManifest,
    SourceDocument,
    StageReceipt,
)
from influence.services.actors import ActorResolver, merge_actors, resolution_summary
from influence.services.law_query import (
    LawQuery,
    com_reference_from_celex,
    parse_query,
    resolve_title,
    title_tokens,
)
from influence.services.passages import document_passages

# Bump when this module's logic changes what a stage writes: it is part of every stage's
# input hash (through the code revision the caller builds from it), so old stages rerun.
COLLECT_REVISION = "collect-3"

DOSSIERS_DUMP = "ep_dossiers"
COMMITTEE_DUMP = "ep_amendments"
PLENARY_DUMP = "ep_plenary_amendments"
MEPS_DUMP = "ep_meps"

COVERAGE_FILE = "coverage.jsonl"
LAW_FILE = "law.jsonl"
DOCUMENTS_FILE = "documents.jsonl"
TEXTS_FILE = "texts.jsonl"
ARTICLES_FILE = "articles.jsonl"
AMENDMENTS_FILE = "amendments.jsonl"
PASSAGES_FILE = "passages.jsonl"
SUBMITTERS_FILE = "submitters.jsonl"
ACTORS_FILE = "actors.jsonl"

# Common names the title search cannot reach, because the name shares no word with the
# official title ("AI Act" against "Artificial Intelligence Act"). An alias is used only
# when its procedure is in the catalog, and a law missing from this table still resolves
# by title, number, CELEX or COM reference.
ALIASES: Mapping[str, str] = {
    "ai act": "2021/0106(COD)",
    "aia": "2021/0106(COD)",
    "dsa": "2020/0361(COD)",
    "dma": "2020/0374(COD)",
    "csddd": "2022/0051(COD)",
    "cs3d": "2022/0051(COD)",
    "ehds": "2022/0140(COD)",
}

# CELLAR negotiates on three-letter codes; every other source writes two letters.
_LANGUAGE_CODES: Mapping[str, str] = {"eng": "en"}
_MEP_PREFIX = "actor:mep:"
_WORD = re.compile(r"[^\W_]+")
# Have Your Say's title search is an AND over the words: a few distinctive ones find the
# initiative, the whole title rarely does.
_SEARCH_WORDS = 3
_LAYERS: tuple[str, ...] = get_args(Layer.__value__)

POSITION_NOT_COLLECTED = (
    "Parliament's position text is not collected: CELLAR's dossier links only the "
    "legislative resolution, which has no articles"
)
NO_CONNECTOR = "No connector for this layer in this run"
NO_COM_REFERENCE = "No COM reference is known for the procedure, so no consultation can be joined"
OPEN_PROCEDURE = (
    "The procedure is not completed: amendments tabled after the Parltrack dump was "
    "produced are not included"
)
REGISTER_UNAVAILABLE = (
    "The Transparency Register export was not read: submitters are identified by name only"
)


class CollectError(Exception):
    """The run cannot continue: a required input is missing, unresolved or invalid.

    `choices` lists the procedures a query could mean when it does not name exactly one.
    """

    def __init__(self, message: str, choices: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.choices = tuple(choices)


class CoverageRecord(AtlasRecord):
    """One coverage row as a stage file, so a reused stage keeps its gaps and reasons."""

    coverage: LayerCoverage


@dataclass(frozen=True)
class CollectResult:
    law: LawRecord
    manifest: RunManifest
    manifest_path: Path
    # The law's bundle directory; every `OutputFile.path` in the manifest is relative to it.
    bundle: Path


_MODELS: Mapping[str, type[AtlasRecord]] = {
    COVERAGE_FILE: CoverageRecord,
    LAW_FILE: LawRecord,
    DOCUMENTS_FILE: SourceDocument,
    TEXTS_FILE: DocumentText,
    ARTICLES_FILE: ArticleVersion,
    AMENDMENTS_FILE: Amendment,
    PASSAGES_FILE: Passage,
    SUBMITTERS_FILE: Actor,
    ACTORS_FILE: Actor,
}


def _quiet(message: str) -> None:
    del message


# --- Paths and small helpers --------------------------------------------------------------


def dump_path(data_root: Path, name: str) -> Path:
    return data_root / "raw" / "parltrack" / f"{name}{parltrack.DUMP_SUFFIX}"


def register_path(data_root: Path) -> Path:
    return data_root / "raw" / "registry" / "register.xml"


def catalog_path(data_root: Path) -> Path:
    return data_root / "catalog" / "procedures.jsonl"


def hys_index_path(data_root: Path) -> Path:
    return data_root / "catalog" / "hys-index.jsonl"


def bundle_path(data_root: Path, procedure_id: str) -> Path:
    return data_root / "laws" / procedure_slug(procedure_id)


def _fingerprint(path: Path) -> str:
    """Size and modification time: enough to notice a replaced input without hashing it."""
    try:
        stat = path.stat()
    except OSError:
        return "absent"
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def _midnight(day: date | None) -> datetime | None:
    """A stated publication day as the start of that day in UTC; the hour is not stated."""
    return None if day is None else datetime(day.year, day.month, day.day, tzinfo=UTC)


def _gap(layer: Layer, status: LayerStatus, reason: str, count: int | None = None) -> LayerCoverage:
    return LayerCoverage(layer=layer, status=status, count=count, reason=reason)


def read_stage_records[T: AtlasRecord](
    bundle: Path, receipt: StageReceipt, name: str, model: type[T]
) -> tuple[T, ...]:
    """The validated records of the stage file called `name`, split at line feeds only.

    Submissions hold characters that Python's `str.splitlines` treats as line ends
    (U+2028, U+2029, U+0085) and that JSON leaves unescaped, so a reader built on
    `splitlines` cuts such a record in two. The writer ends each record with a line
    feed and escapes every line feed inside a record, so that is the only separator.
    """
    for output in receipt.outputs:
        if Path(output.path).name == name:
            lines = (bundle / output.path).read_bytes().split(b"\n")[:-1]
            try:
                return tuple(model.model_validate_json(line) for line in lines)
            except ValidationError as error:
                raise CollectError(
                    f"{output.path} of stage {receipt.stage} failed validation: {error}"
                ) from error
    raise CollectError(f"Stage {receipt.stage} has no output named {name}")


# --- Resolving the query ------------------------------------------------------------------


def load_catalog(data_root: Path) -> tuple[parltrack.ProcedureEntry, ...]:
    """The procedure catalog, built from the dossier dump the first time (about 10 s)."""
    path = catalog_path(data_root)
    try:
        if not path.exists():
            dossiers = dump_path(data_root, DOSSIERS_DUMP)
            parltrack.write_catalog(parltrack.build_catalog(dossiers), path)
        return tuple(parltrack.read_catalog(path))
    except parltrack.ParltrackError as error:
        raise CollectError(f"The procedure catalog cannot be built or read: {error}") from error


def _references(
    query: LawQuery, catalog: Sequence[parltrack.ProcedureEntry], fetcher: CachedFetcher
) -> tuple[str, ...]:
    """Procedures a CELEX or COM number names: the catalog first, CELLAR when it has none."""
    com = query.value if query.kind == "com" else com_reference_from_celex(query.value)
    if query.kind == "celex":
        celex = query.value
    else:
        year, number = query.value.removeprefix("COM(").split(")")
        celex = f"5{year}PC{int(number):04d}"
    matches = tuple(
        entry.procedure_id
        for entry in catalog
        if entry.celex_final == celex or (com is not None and com in entry.com_references)
    )
    if matches:
        return matches
    try:
        return cellar.procedures_for_celex(fetcher, celex)
    except cellar.CellarError as error:
        raise CollectError(f"CELLAR could not resolve {query.value}: {error}") from error


def resolve_procedure(
    query: LawQuery, catalog: Sequence[parltrack.ProcedureEntry], fetcher: CachedFetcher
) -> parltrack.ProcedureEntry:
    """Exactly one catalog entry, or a `CollectError` that lists the choices when several."""
    by_id = {entry.procedure_id: entry for entry in catalog}
    if query.kind == "title":
        resolution = resolve_title(
            query.value, ((entry.procedure_id, entry.title) for entry in catalog), ALIASES
        )
        if resolution.chosen is None:
            problem = "matches several procedures" if resolution.ambiguous else "matches no title"
            raise CollectError(
                f"{query.value!r} {problem} in the procedure catalog",
                [f"{item.procedure_id}  {item.title}" for item in resolution.candidates],
            )
        return by_id[resolution.chosen.procedure_id]
    references = (
        (query.value,) if query.kind == "procedure" else _references(query, catalog, fetcher)
    )
    known = [by_id[reference] for reference in references if reference in by_id]
    if len(known) != 1:
        problem = "names several procedures" if known else "is not a procedure in the catalog"
        raise CollectError(
            f"{query.value} {problem} (Parltrack dossiers)",
            [f"{entry.procedure_id}  {entry.title}" for entry in known],
        )
    return known[0]


# --- Stages -------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Built:
    """What a stage produced: its record files, its coverage rows, and what went wrong.

    `errors` holds only failures that may not repeat. A gap the source will always have
    belongs in a coverage row's reason, so the stage can still be reused.
    """

    files: Mapping[str, Sequence[AtlasRecord]]
    coverage: Sequence[LayerCoverage]
    counts: Mapping[str, int]
    errors: Sequence[str] = ()


@dataclass(frozen=True)
class _Run:
    """What every stage of one run shares."""

    entry: parltrack.ProcedureEntry
    data_root: Path
    store: StageStore
    fetcher: CachedFetcher
    started: datetime
    code_revision: str
    timer: Callable[[], float]
    progress: Callable[[str], None]

    @property
    def procedure_id(self) -> str:
        return self.entry.procedure_id

    def stage(self, name: str, inputs: Sequence[str], build: Callable[[], _Built]) -> StageReceipt:
        """Reuse the stage when its inputs are unchanged and it ended clean; else run it."""
        key = input_hash(name, self.procedure_id, self.code_revision, *inputs)
        receipt = self.store.load(name, key)
        if receipt is not None and not receipt.errors:
            self.progress(f"{name}: reused")
            return receipt
        self.progress(f"{name}: running")
        started = self.timer()
        built = build()
        files: dict[str, Sequence[AtlasRecord]] = {
            **built.files,
            COVERAGE_FILE: [CoverageRecord(coverage=row) for row in built.coverage],
        }
        return self.store.save(
            name,
            key,
            files,
            status="partial" if built.errors else "complete",
            seconds=self.timer() - started,
            counts=built.counts,
            errors=built.errors,
        )

    def coverage(self, receipt: StageReceipt) -> list[LayerCoverage]:
        records = read_stage_records(self.store.root, receipt, COVERAGE_FILE, CoverageRecord)
        return [record.coverage for record in records]


def _law_texts(run: _Run, celex_proposal: str | None, celex_final: str | None) -> _Built:
    documents: list[SourceDocument] = []
    texts: list[DocumentText] = []
    articles: list[ArticleVersion] = []
    coverage: list[LayerCoverage] = []
    counts: dict[str, int] = {}
    errors: list[str] = []
    wanted: tuple[tuple[ArticleStage, str | None, date | None], ...] = (
        # The proposal prints no date of its own; Parltrack states when it was published.
        ("proposal", celex_proposal, run.entry.proposed_on),
        ("final_act", celex_final, None),
    )
    for stage, celex, stated_on in wanted:
        if celex is None:
            if stage == "final_act" and run.entry.status in ("ongoing", "withdrawn"):
                reason = f"The procedure is {run.entry.status}: there is no final act"
                coverage.append(_gap(stage, "not_applicable", reason))
            else:
                reason = "Neither CELLAR nor Parltrack names one CELEX number for this text"
                coverage.append(_gap(stage, "missing", reason))
            continue
        identifier = cellar.cellar_document_id(celex)
        try:
            act = cellar.fetch_act(run.fetcher, celex)
            if isinstance(act, cellar.MissingAct):
                if act.status == "missing":
                    coverage.append(_gap(stage, "missing", f"CELLAR has no text for {celex}"))
                else:
                    errors.append(f"{celex}: {act.reason}")
                    coverage.append(_gap(stage, "not_collected", f"{celex}: {act.reason}"))
                continue
            split = cellar.split_provisions(
                act.body,
                procedure_id=run.procedure_id,
                celex=celex,
                stage=stage,
                document_id=identifier,
                version_date=stated_on,
            )
        except cellar.CellarError as error:
            errors.append(f"{celex}: {error}")
            coverage.append(_gap(stage, "not_collected", f"{celex}: {error}"))
            continue
        published_on = split.published_on or stated_on
        document = cellar.source_document(
            act,
            procedure_id=run.procedure_id,
            extraction_status="extracted" if split.provisions else "partial",
            text_characters=len(split.document_text.text),
            published_at=_midnight(published_on),
        )
        language = _LANGUAGE_CODES.get(act.language, act.language)
        documents.append(document.model_copy(update={"language": language}))
        texts.append(split.document_text)
        articles.extend(split.provisions)
        counts[f"{stage}_provisions"] = len(split.provisions)
        coverage.append(
            LayerCoverage(
                layer=stage,
                status="complete" if split.provisions else "partial",
                count=len(split.provisions),
                reason=split.reason,
                source_updated_on=published_on,
            )
        )
    coverage.append(_gap("parliament_position", "not_collected", POSITION_NOT_COLLECTED))
    files = {DOCUMENTS_FILE: documents, TEXTS_FILE: texts, ARTICLES_FILE: articles}
    return _Built(files, coverage, counts, errors)


type _AmendmentReader = Callable[[Path, str, datetime, Counter[str] | None], Iterator[Amendment]]


def _amendments(run: _Run) -> _Built:
    documents: list[SourceDocument] = []
    amendments: list[Amendment] = []
    coverage: list[LayerCoverage] = []
    counts: dict[str, int] = {}
    errors: list[str] = []
    sources: tuple[tuple[Layer, str, str, _AmendmentReader], ...] = (
        ("committee_amendments", "committee", COMMITTEE_DUMP, parltrack.committee_amendments),
        ("plenary_amendments", "plenary", PLENARY_DUMP, parltrack.plenary_amendments),
    )
    for layer, label, dump, reader in sources:
        path = dump_path(run.data_root, dump)
        skipped = Counter[str]()
        try:
            found = list(reader(path, run.procedure_id, run.started, skipped))
            # The dump was retrieved when it was written to disk, not when this run reads it.
            retrieved_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            documents.append(parltrack.dump_source_document(path, retrieved_at))
        except parltrack.ParltrackError as error:
            errors.append(str(error))
            coverage.append(_gap(layer, "not_collected", str(error)))
            continue
        amendments.extend(found)
        counts[label] = len(found)
        counts.update({f"{label}_skipped_{reason}": times for reason, times in skipped.items()})
        if not found:
            reason = f"The Parltrack dump {dump} holds no amendment for this procedure"
            coverage.append(_gap(layer, "missing", reason, 0))
        elif run.entry.status != "completed":
            coverage.append(_gap(layer, "partial", OPEN_PROCEDURE, len(found)))
        else:
            coverage.append(LayerCoverage(layer=layer, status="complete", count=len(found)))
    return _Built(
        {DOCUMENTS_FILE: documents, AMENDMENTS_FILE: amendments}, coverage, counts, errors
    )


@dataclass(frozen=True)
class _Consultation:
    """The Have Your Say publications joined to the law, and why some may be absent."""

    publication_ids: tuple[int, ...]
    index_hits: int
    gaps: tuple[str, ...]
    errors: tuple[str, ...]


def _search_words(title: str) -> str:
    distinctive = title_tokens(title)
    words = dict.fromkeys(word for word in _WORD.findall(title) if word.lower() in distinctive)
    return " ".join(list(words)[:_SEARCH_WORDS])


def find_consultation(
    data_root: Path, fetcher: CachedFetcher, com_reference: str | None, title: str
) -> _Consultation:
    """Join the law to its consultation by COM reference: the index, then a title search.

    The index may be absent or still being crawled, so a COM reference it does not hold
    is looked up through the portal's title search, where the COM reference on a
    publication still decides. Every stage of each initiative is returned (roadmap,
    consultation, proposal feedback).
    """
    if com_reference is None:
        return _Consultation((), 0, (NO_COM_REFERENCE,), ())
    gaps: list[str] = []
    errors: list[str] = []
    try:
        found = hys.find_initiatives(hys.read_index(hys_index_path(data_root)), com_reference)
    except hys.HysError:
        # No usable index is not a gap in the law: the title search below answers instead.
        found = ()
    index_hits = len(found)
    if not found:
        try:
            found = hys.find_by_title(fetcher, _search_words(title), com_reference)
        except hys.HysError as error:
            errors.append(f"Have Your Say title search failed: {error}")
    if not found:
        gaps.append(f"No Have Your Say initiative was found for {com_reference}")
    publications = dict.fromkeys(
        publication.publication_id for entry in found for publication in entry.publications
    )
    return _Consultation(tuple(publications), index_hits, tuple(gaps), tuple(errors))


def _register_entries(data_root: Path, errors: list[str]) -> list[RegisterEntry]:
    try:
        return list(iter_register(register_path(data_root)))
    except RegisterError as error:
        errors.append(str(error))
        return []


def _asks(
    run: _Run, consultation: _Consultation, com_reference: str | None, limit: int | None
) -> _Built:
    """Feedback, attachments and their passages, each passage attributed to one actor.

    Attachments are the slow part (a download and a PDF extraction each). Downloads go
    through the HTTP cache, so an interrupted run resumes where it stopped, and `limit`
    reads only the first attachments for a fast first run; the rest are then a stated gap.
    """
    gaps = list(consultation.gaps)
    errors = list(consultation.errors)
    items: dict[int, tuple[hys.FeedbackItem, str]] = {}
    # An item is counted under the first publication that served it.
    origin: dict[int, int] = {}
    unavailable = 0
    for publication_id in consultation.publication_ids:
        try:
            for position, item in enumerate(hys.iter_feedback(run.fetcher, publication_id)):
                url = hys.feedback_url(publication_id, position // hys.PAGE_SIZE)
                items.setdefault(item.feedback_id, (item, url))
                origin.setdefault(item.feedback_id, publication_id)
        except hys.HysUnavailable as error:
            unavailable += 1
            gaps.append(str(error))
        except hys.HysError as error:
            errors.append(f"Publication {publication_id}: {error}")
    # The register is 117 MB: it is read only when there is somebody to identify.
    entries = _register_entries(run.data_root, errors) if items else []
    resolver = ActorResolver.build(entries)
    documents: list[SourceDocument] = []
    texts: list[DocumentText] = []
    passages: list[Passage] = []
    submitters: list[Actor] = []
    pending: dict[str, tuple[hys.Attachment, hys.FeedbackItem, str]] = {}
    for item, url in items.values():
        document, text = hys.feedback_records(
            item, procedure_id=run.procedure_id, retrieved_at=run.started, url=url
        )
        actor = resolver.resolve(
            item.organization,
            register_id=item.register_id,
            source_kind="hys_feedback",
            user_type=item.user_type,
            country=item.country,
            document_id=document.document_id,
        )
        submitters.append(actor)
        documents.append(document)
        texts.append(text)
        passages.extend(
            document_passages(
                document,
                text,
                procedure_id=run.procedure_id,
                actor_id=actor.actor_id,
                submitted_at=item.submitted_at,
            )
        )
        for attachment in item.attachments:
            pending.setdefault(attachment.document_id, (attachment, item, actor.actor_id))
    chosen = list(pending.values())[:limit]
    failed = 0
    unreadable = 0
    for number, (attachment, item, actor_id) in enumerate(chosen, start=1):
        run.progress(f"asks: attachment {number} of {len(chosen)}")
        try:
            document, attached = hys.fetch_attachment(
                run.fetcher, attachment, item, procedure_id=run.procedure_id
            )
        except hys.HysError as error:
            failed += 1
            errors.append(str(error))
            continue
        if item.is_citizen:
            # A private person's file name can be their own name: counted, never named.
            document = document.model_copy(update={"title": None})
        documents.append(document)
        if attached is None:
            unreadable += 1
            continue
        texts.append(attached)
        passages.extend(
            document_passages(
                document,
                attached,
                procedure_id=run.procedure_id,
                actor_id=actor_id,
                submitted_at=item.submitted_at,
            )
        )
    without_text = sum(1 for item, _ in items.values() if not item.text.strip())
    # Per publication, so a run can be checked against the portal's own totals.
    served = Counter[str]()
    for item, _ in items.values():
        prefix = f"publication_{origin[item.feedback_id]}"
        served[f"{prefix}_feedback"] += 1
        served[f"{prefix}_with_register_id"] += bool(item.register_id)
        served[f"{prefix}_with_attachments"] += bool(item.attachments)
    reasons = [*gaps, *errors]
    if without_text:
        # The portal serves some submissions with no text at all (most of the DSA's).
        reasons.append(f"{without_text} of {len(items)} feedback items carry no text")
    if len(chosen) < len(pending):
        reasons.append(f"Attachment limit: {len(chosen)} of {len(pending)} attachments read")
    if unreadable:
        reasons.append(f"{unreadable} attachments have no extractable text")
    if items:
        status: LayerStatus = "partial" if reasons else "complete"
        reason = "; ".join(reasons) or None
    else:
        status = "not_collected" if errors or com_reference is None else "missing"
        reason = "; ".join(reasons) or "The consultation holds no feedback"
    counts = {
        "initiatives_from_index": consultation.index_hits,
        "publications": len(consultation.publication_ids),
        "publications_unavailable": unavailable,
        "feedback": len(items),
        "feedback_without_text": without_text,
        "feedback_with_register_id": sum(1 for item, _ in items.values() if item.register_id),
        "feedback_from_citizens": sum(1 for item, _ in items.values() if item.is_citizen),
        "feedback_with_attachments": sum(1 for item, _ in items.values() if item.attachments),
        **served,
        "attachments_listed": len(pending),
        "attachments_read": len(chosen) - failed,
        "attachments_failed_download": failed,
        "attachments_without_text": unreadable,
        "passages": len(passages),
        "register_entries": len(entries),
    }
    files = {
        DOCUMENTS_FILE: documents,
        TEXTS_FILE: texts,
        PASSAGES_FILE: passages,
        SUBMITTERS_FILE: merge_actors(submitters),
    }
    coverage = [LayerCoverage(layer="asks", status=status, count=len(items), reason=reason)]
    return _Built(files, coverage, counts, errors)


def _actors(
    run: _Run, amendments: Sequence[Amendment], submitters: Sequence[Actor], *, register_read: bool
) -> _Built:
    mep_ids = sorted(
        {
            int(author.removeprefix(_MEP_PREFIX))
            for amendment in amendments
            for author in amendment.author_ids
        }
    )
    errors: list[str] = []
    reasons: list[str] = []
    skipped = Counter[str]()
    try:
        members = list(parltrack.mep_actors(dump_path(run.data_root, MEPS_DUMP), mep_ids, skipped))
    except parltrack.ParltrackError as error:
        members = []
        errors.append(str(error))
        reasons.append(str(error))
    if len(members) < len(mep_ids):
        absent = len(mep_ids) - len(members)
        reasons.append(f"{absent} of {len(mep_ids)} amendment authors have no Member record")
    if not register_read:
        reasons.append(REGISTER_UNAVAILABLE)
    actors = merge_actors([*submitters, *members])
    if actors:
        status: LayerStatus = "partial" if reasons else "complete"
        reason = "; ".join(reasons) or None
    else:
        status = "missing"
        reason = "; ".join(reasons) or "No amendment author and no submitter is named"
    counts = {
        **resolution_summary(actors),
        "amendment_authors": len(mep_ids),
        "members_found": len(members),
        **{f"members_skipped_{name}": times for name, times in skipped.items()},
    }
    coverage = [LayerCoverage(layer="actors", status=status, count=len(actors), reason=reason)]
    return _Built({ACTORS_FILE: actors}, coverage, counts, errors)


# --- The run ------------------------------------------------------------------------------


def _output_hashes(receipt: StageReceipt) -> str:
    return ",".join(output.sha256 for output in receipt.outputs)


def collect_law(
    query: str,
    *,
    data_root: Path,
    fetcher: CachedFetcher,
    clock: Callable[[], datetime],
    code_revision: str,
    attachment_limit: int | None = None,
    hardware: str | None = None,
    timer: Callable[[], float] = time.perf_counter,
    progress: Callable[[str], None] = _quiet,
) -> CollectResult:
    """Resolve `query` to one law, write its record under `data_root/laws/<slug>/`.

    `clock` must return aware datetimes. `attachment_limit` None reads every attachment.
    The manifest is published only after every stage file has been read back and
    validated against its record contract, so `manifest.json` never names a bad file.
    Raises `CollectError` when the query does not resolve to exactly one procedure, when
    the law has neither amendments nor asks, or when a stage file fails validation.
    """
    started = clock()
    try:
        parsed = parse_query(query)
    except ValueError as error:
        raise CollectError(str(error)) from error
    entry = resolve_procedure(parsed, load_catalog(data_root), fetcher)
    procedure_id = entry.procedure_id
    progress(f"resolved: {procedure_id} {entry.title}")

    metadata_reasons: list[str] = []
    try:
        # An open procedure's answer goes stale the day its act is published.
        identifiers = cellar.resolve_celex(
            fetcher, procedure_id, refresh=entry.status != "completed"
        )
    except cellar.CellarError as error:
        metadata_reasons.append(f"CELLAR identifiers not resolved: {error}")
        identifiers = cellar.LawIdentifiers(
            procedure_id=procedure_id, celex_proposal=None, celex_final=None, com_reference=None
        )
    if identifiers.ambiguous:
        listed = ", ".join((*identifiers.proposal_candidates, *identifiers.final_candidates))
        metadata_reasons.append(f"CELLAR lists several acts for one procedure: {listed}")
    # CELLAR's answer wins whenever it lists a final act, including "several, so none".
    celex_final = identifiers.celex_final if identifiers.final_candidates else entry.celex_final
    stated = entry.com_references
    com_reference = identifiers.com_reference or (stated[0] if len(stated) == 1 else None)

    bundle = bundle_path(data_root, procedure_id)
    run = _Run(
        entry=entry,
        data_root=data_root,
        store=StageStore(bundle),
        fetcher=fetcher,
        started=started,
        code_revision=code_revision,
        timer=timer,
        progress=progress,
    )
    law_texts = run.stage(
        "law_texts",
        (identifiers.celex_proposal or "", celex_final or "", str(entry.proposed_on)),
        lambda: _law_texts(run, identifiers.celex_proposal, celex_final),
    )
    amendments = run.stage(
        "amendments",
        (
            _fingerprint(dump_path(data_root, COMMITTEE_DUMP)),
            _fingerprint(dump_path(data_root, PLENARY_DUMP)),
        ),
        lambda: _amendments(run),
    )
    consultation = find_consultation(data_root, fetcher, com_reference, entry.title)
    asks = run.stage(
        "asks",
        (
            com_reference or "",
            ",".join(str(identifier) for identifier in sorted(consultation.publication_ids)),
            str(attachment_limit),
            _fingerprint(register_path(data_root)),
        ),
        lambda: _asks(run, consultation, com_reference, attachment_limit),
    )
    tabled = amendments.counts.get("committee", 0) + amendments.counts.get("plenary", 0)
    feedback = asks.counts["feedback"]
    if tabled == 0 and feedback == 0:
        gaps = [*run.coverage(amendments), *run.coverage(asks)]
        raise CollectError(
            f"{procedure_id} has no amendments and no asks, so there is nothing to link: "
            + "; ".join(f"{gap.layer}: {gap.reason}" for gap in gaps)
        )
    actors = run.stage(
        "actors",
        (
            _output_hashes(amendments),
            _output_hashes(asks),
            _fingerprint(dump_path(data_root, MEPS_DUMP)),
        ),
        lambda: _actors(
            run,
            read_stage_records(bundle, amendments, AMENDMENTS_FILE, Amendment),
            read_stage_records(bundle, asks, SUBMITTERS_FILE, Actor),
            register_read=feedback == 0 or asks.counts["register_entries"] > 0,
        ),
    )
    own = [
        LayerCoverage(
            layer="metadata",
            status="partial" if metadata_reasons else "complete",
            reason="; ".join(metadata_reasons) or None,
        ),
        _gap("meetings", "not_collected", NO_CONNECTOR),
        _gap("votes", "not_collected", NO_CONNECTOR),
    ]
    rows = [
        *own,
        *(row for stage in (law_texts, amendments, asks, actors) for row in run.coverage(stage)),
    ]
    coverage = tuple(sorted(rows, key=lambda row: _LAYERS.index(row.layer)))
    law = LawRecord(
        procedure_id=procedure_id,
        title=entry.title,
        status=entry.status,
        stage_reached=entry.stage_reached,
        celex_proposal=identifiers.celex_proposal,
        celex_final=celex_final,
        com_reference=com_reference,
        subjects=entry.subjects,
        lead_committee=entry.lead_committee,
        proposed_on=entry.proposed_on,
        completed_on=entry.completed_on,
        coverage=coverage,
    )
    metadata = run.stage(
        "metadata",
        (law.model_dump_json(),),
        lambda: _Built({LAW_FILE: [law]}, own, {"layers": len(coverage)}),
    )
    receipts = (metadata, law_texts, amendments, asks, actors)
    for receipt in receipts:
        for output in receipt.outputs:
            name = Path(output.path).name
            read_stage_records(bundle, receipt, name, _MODELS[name])
    manifest = RunManifest(
        run_id=f"{procedure_slug(procedure_id)}-{started.astimezone(UTC):%Y%m%dT%H%M%SZ}",
        query=query,
        procedure_id=procedure_id,
        status="complete",
        started_at=started,
        completed_at=clock(),
        code_revision=code_revision,
        config={"attachment_limit": "all" if attachment_limit is None else str(attachment_limit)},
        hardware=hardware,
        stages=receipts,
        coverage=coverage,
    )
    manifest_path = run.store.publish(manifest)
    return CollectResult(law=law, manifest=manifest, manifest_path=manifest_path, bundle=bundle)
