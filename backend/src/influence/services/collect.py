"""Part 1 · Collect: one law query in, that law's public record out, as Atlas records.

This joins the connectors that already exist, one per source family (docs/plan.md §5).
The procedure catalog built from Parltrack's dossiers resolves what was typed; CELLAR gives
the proposal and the final act; Parltrack gives the amendments and the MEPs who tabled
them; Have Your Say, joined by COM reference only, gives the submissions, split into
passages; the Transparency Register resolves who sent them. Nothing here names a law: a
procedure number, CELEX, COM reference or title all take the same path.

Every stage saves through `StageStore`, keyed by its inputs and the source revision, so a
rerun reuses finished work and a code change redoes it. Each stage also saves a partial
`LawRecord` with the identifiers it learned and the coverage of its layers, so a reused
stage still reports its gaps. A missing required input stops the run before any work; an
optional source that fails becomes a labelled gap (plan §6). The run manifest is
published last, after every output re-verifies.
"""

import hashlib
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from time import perf_counter
from typing import Self

from influence.extraction.cache import request_key
from influence.extraction.fetching import CachedFetcher
from influence.extraction.layout import procedure_slug
from influence.extraction.records import StageStore, input_hash
from influence.repositories import cellar, hys, parltrack
from influence.repositories.parltrack import ParltrackError, ProcedureEntry
from influence.repositories.register import RegisterError, iter_register
from influence.schemas.atlas import (
    Actor,
    ArticleStage,
    ArticleVersion,
    AtlasRecord,
    DocumentText,
    LawRecord,
    Layer,
    LayerCoverage,
    Passage,
    RunManifest,
    SourceDocument,
    StageReceipt,
    StageStatus,
)
from influence.services.actors import ActorResolver, merge_actors, resolution_summary
from influence.services.law_query import parse_query, resolve_title
from influence.services.passages import document_passages

LAYERS: tuple[Layer, ...] = (
    "metadata",
    "proposal",
    "parliament_position",
    "final_act",
    "committee_amendments",
    "plenary_amendments",
    "asks",
    "actors",
    "meetings",
    "votes",
)
PARLIAMENT_POSITION_GAP = (
    "CELLAR files only Parliament's legislative resolution, not its consolidated position "
    "text, and the EP API adopted-texts connector is not built"
)
NOT_BUILT_GAP = "No connector for this layer is built yet"
_COM = re.compile(r"COM\((\d{4})\)(\d+)")
_MEP_PREFIX = "actor:mep:"
_HASH_CHUNK_BYTES = 1 << 20


class CollectError(RuntimeError):
    """No bundle can be built: a required input is missing or the law is not identified."""


class AmbiguousLawError(CollectError):
    """The query fits several procedures; analysing the wrong one would look just as real."""

    def __init__(self, query: str, choices: Sequence[tuple[str, str]]) -> None:
        listed = "; ".join(f"{procedure} {title}" for procedure, title in choices)
        super().__init__(f"{query!r} matches several procedures: {listed}")
        self.choices = tuple(choices)


@dataclass(frozen=True)
class CollectInputs:
    """The global files a run reads. Parltrack dumps keep their published file names."""

    dossiers: Path
    committee_amendments: Path
    plenary_amendments: Path
    meps: Path
    register: Path
    # Optional: without it the consultation is found by a labelled title search.
    hys_index: Path

    @classmethod
    def under(cls, data_root: Path) -> Self:
        parltrack_dumps = data_root / "raw" / "parltrack"
        return cls(
            dossiers=parltrack_dumps / "ep_dossiers.json.zst",
            committee_amendments=parltrack_dumps / "ep_amendments.json.zst",
            plenary_amendments=parltrack_dumps / "ep_plenary_amendments.json.zst",
            meps=parltrack_dumps / "ep_meps.json.zst",
            register=data_root / "raw" / "registry" / "register.xml",
            hys_index=data_root / "catalog" / "hys-index.jsonl",
        )

    def missing(self) -> tuple[Path, ...]:
        required = (
            self.dossiers,
            self.committee_amendments,
            self.plenary_amendments,
            self.meps,
            self.register,
        )
        return tuple(path for path in required if not path.is_file())


@dataclass(frozen=True)
class CollectSettings:
    data_root: Path
    # Part of every stage key, so receipts written by other code are never reused.
    code_revision: str
    attachments: bool = True
    refresh: bool = False
    hardware: str | None = None


@dataclass(frozen=True)
class ResolvedLaw:
    procedure_id: str
    # None when the dossiers dump does not hold the procedure (newer than the dump).
    entry: ProcedureEntry | None


@dataclass(frozen=True)
class CollectResult:
    law: LawRecord
    manifest: RunManifest
    manifest_path: Path
    bundle: Path


def source_revision(package: Path) -> str:
    """`src-<12 hex>`: a hash of every Python file of the package, in path order.

    Unlike a commit hash it changes with uncommitted edits, which is what decides whether
    a saved stage may be reused. Linear in the package's size (well under a megabyte).
    """
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
        digest.update(b"\x00")
    return f"src-{digest.hexdigest()[:12]}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def load_catalog(dossiers: Path, directory: Path) -> tuple[ProcedureEntry, ...]:
    """The procedure catalog, built once per dossiers file: its name carries the file hash.

    Building reads every dossier (about 10 s for 23,885 of them); reading it back is fast.
    """
    path = directory / f"procedures-{file_sha256(dossiers)[:16]}.jsonl"
    try:
        if not path.is_file():
            parltrack.write_catalog(parltrack.build_catalog(dossiers), path)
        return tuple(parltrack.read_catalog(path))
    except ParltrackError as error:
        raise CollectError(f"The procedure catalog cannot be built: {error}") from error


def proposal_celex(com_reference: str) -> str | None:
    """`COM(2021)206` is the proposal `52021PC0206`; None when the text is no COM reference."""
    match = _COM.fullmatch(com_reference)
    if match is None:
        return None
    return f"5{match.group(1)}PC{int(match.group(2)):04d}"


def resolve_law(
    text: str, catalog: Sequence[ProcedureEntry], fetcher: CachedFetcher
) -> ResolvedLaw:
    """Identify one procedure from what was typed, or say why that is not possible.

    The local catalog answers first; CELLAR is asked only for a CELEX or COM number the
    catalog does not hold. A title is never sent anywhere: it is matched locally, and a
    close race returns the choices instead of a guess. Linear in the catalog's size.
    """
    try:
        query = parse_query(text)
    except ValueError as error:
        raise CollectError(str(error)) from error
    by_id = {entry.procedure_id: entry for entry in catalog}
    if query.kind == "procedure":
        return ResolvedLaw(query.value, by_id.get(query.value))
    if query.kind == "title":
        resolution = resolve_title(query.value, ((e.procedure_id, e.title) for e in catalog))
        if resolution.chosen is not None:
            return ResolvedLaw(
                resolution.chosen.procedure_id, by_id[resolution.chosen.procedure_id]
            )
        if resolution.candidates:
            raise AmbiguousLawError(
                text, [(c.procedure_id, c.title) for c in resolution.candidates]
            )
        raise CollectError(f"No procedure title in the catalog matches {query.value!r}")
    if query.kind == "celex":
        found = tuple(e.procedure_id for e in catalog if e.celex_final == query.value)
        celex: str | None = query.value
    else:
        found = tuple(e.procedure_id for e in catalog if query.value in e.com_references)
        celex = proposal_celex(query.value)
    if not found and celex is not None:
        try:
            found = cellar.procedures_for_celex(fetcher, celex)
        except cellar.CellarError as error:
            raise CollectError(f"CELLAR could not resolve {celex}: {error}") from error
    match found:
        case ():
            raise CollectError(f"No procedure is known for {query.value}")
        case (procedure_id,):
            return ResolvedLaw(procedure_id, by_id.get(procedure_id))
        case _:
            choices = [(p, by_id[p].title if p in by_id else p) for p in sorted(set(found))]
            raise AmbiguousLawError(text, choices)


# --- Stages ---------------------------------------------------------------------------------


_TEXTS_FILES = ("documents.jsonl", "document_texts.jsonl", "articles.jsonl")
_ASKS_FILES = ("documents.jsonl", "document_texts.jsonl", "passages.jsonl", "actors.jsonl")


def _files(names: Iterable[str], *, law: LawRecord) -> dict[str, tuple[AtlasRecord, ...]]:
    """A stage's full set of files, empty but present, so every reader finds every name."""
    return {"law.jsonl": (law,)} | dict.fromkeys(names, ())


@dataclass(frozen=True)
class _Built:
    files: dict[str, tuple[AtlasRecord, ...]]
    counts: dict[str, int]
    errors: tuple[str, ...] = ()

    @property
    def status(self) -> StageStatus:
        return "partial" if self.errors else "complete"


@dataclass(frozen=True)
class _Run:
    store: StageStore
    fetcher: CachedFetcher
    inputs: CollectInputs
    settings: CollectSettings
    law: ResolvedLaw
    started_at: datetime
    receipts: list[StageReceipt] = field(default_factory=list[StageReceipt])

    def stage(self, name: str, inputs: str, build: Callable[[], _Built]) -> StageReceipt:
        """Reuse the saved stage for these inputs, or build it and save its receipt."""
        receipt = None if self.settings.refresh else self.store.load(name, inputs)
        if receipt is None:
            started = perf_counter()
            built = build()
            receipt = self.store.save(
                name,
                inputs,
                built.files,
                status=built.status,
                seconds=perf_counter() - started,
                counts=built.counts,
                errors=built.errors,
            )
        self.receipts.append(receipt)
        return receipt

    def law_record(
        self,
        coverage: Iterable[LayerCoverage],
        *,
        celex_proposal: str | None = None,
        celex_final: str | None = None,
        com_reference: str | None = None,
    ) -> LawRecord:
        """What the catalog says about the law, with a stage's identifiers and coverage.

        CELLAR's identifiers win over the catalog's; the catalog fills only what CELLAR
        did not give, and an identifier neither confirms stays None.
        """
        entry = self.law.entry
        catalog_com = entry.com_references[0] if entry and len(entry.com_references) == 1 else None
        return LawRecord(
            procedure_id=self.law.procedure_id,
            title=entry.title if entry else self.law.procedure_id,
            status=entry.status if entry else "unknown",
            stage_reached=entry.stage_reached if entry else None,
            celex_proposal=celex_proposal,
            celex_final=celex_final or (entry.celex_final if entry else None),
            com_reference=com_reference or catalog_com,
            subjects=entry.subjects if entry else (),
            lead_committee=entry.lead_committee if entry else None,
            proposed_on=entry.proposed_on if entry else None,
            completed_on=entry.completed_on if entry else None,
            coverage=tuple(coverage),
        )

    @property
    def ongoing(self) -> bool:
        return self.law.entry is not None and self.law.entry.status == "ongoing"


def _published_at(day: date | None) -> datetime | None:
    return None if day is None else datetime(day.year, day.month, day.day, tzinfo=UTC)


def _act(
    run: _Run, celex: str, stage: ArticleStage
) -> tuple[tuple[AtlasRecord, ...], LayerCoverage]:
    """One act's provenance, text and provisions, or the reason there are none."""
    fetched = cellar.fetch_act(run.fetcher, celex, refresh=run.settings.refresh)
    if isinstance(fetched, cellar.MissingAct):
        status = "missing" if fetched.status == "missing" else "not_collected"
        return (), LayerCoverage(layer=stage, status=status, reason=f"{celex}: {fetched.reason}")
    try:
        split = cellar.split_provisions(
            fetched.body,
            procedure_id=run.law.procedure_id,
            celex=celex,
            stage=stage,
            document_id=cellar.cellar_document_id(celex),
            version_date=None,
        )
    except cellar.CellarError as error:
        return (), LayerCoverage(layer=stage, status="not_collected", reason=f"{celex}: {error}")
    document = cellar.source_document(
        fetched,
        procedure_id=run.law.procedure_id,
        extraction_status="extracted" if split.provisions else "partial",
        text_characters=len(split.document_text.text),
        published_at=_published_at(split.published_on),
    )
    coverage = LayerCoverage(
        layer=stage,
        status="complete" if split.provisions else "partial",
        count=len(split.provisions),
        reason=None if split.provisions else f"{celex}: {split.reason}",
    )
    return (document, split.document_text, *split.provisions), coverage


def _no_act(stage: ArticleStage, candidates: tuple[str, ...], ongoing: bool) -> LayerCoverage:
    if len(candidates) > 1:
        reason = f"CELLAR lists several: {', '.join(candidates)}; none is chosen"
        return LayerCoverage(layer=stage, status="not_collected", reason=reason)
    if stage == "final_act" and ongoing:
        return LayerCoverage(layer=stage, status="not_applicable", reason="Procedure ongoing")
    return LayerCoverage(layer=stage, status="missing", reason="CELLAR lists none")


def _texts(run: _Run) -> _Built:
    """Stage 1: the proposal and the final act from CELLAR, split into provisions."""
    position = LayerCoverage(
        layer="parliament_position", status="not_collected", reason=PARLIAMENT_POSITION_GAP
    )
    try:
        ids = cellar.resolve_celex(run.fetcher, run.law.procedure_id, refresh=run.settings.refresh)
    except cellar.CellarError as error:
        reason = f"CELLAR did not answer: {error}"
        gaps = [
            LayerCoverage(layer=layer, status="not_collected", reason=reason)
            for layer in ("proposal", "final_act")
        ]
        law = run.law_record([*gaps, position])
        return _Built(_files(_TEXTS_FILES, law=law), {"articles": 0}, (reason,))
    records: list[AtlasRecord] = []
    acts: list[LayerCoverage] = []
    stages: tuple[tuple[ArticleStage, str | None, tuple[str, ...]], ...] = (
        ("proposal", ids.celex_proposal, ids.proposal_candidates),
        ("final_act", ids.celex_final, ids.final_candidates),
    )
    for stage, celex, candidates in stages:
        if celex is None:
            acts.append(_no_act(stage, candidates, run.ongoing))
            continue
        found, layer = _act(run, celex, stage)
        records.extend(found)
        acts.append(layer)
    law = run.law_record(
        [position, *acts],
        celex_proposal=ids.celex_proposal,
        celex_final=ids.celex_final,
        com_reference=ids.com_reference,
    )
    errors = tuple(item.reason or "" for item in acts if item.status == "not_collected")
    return _Built(
        {
            "law.jsonl": (law,),
            "documents.jsonl": tuple(r for r in records if isinstance(r, SourceDocument)),
            "document_texts.jsonl": tuple(r for r in records if isinstance(r, DocumentText)),
            "articles.jsonl": tuple(r for r in records if isinstance(r, ArticleVersion)),
        },
        {"articles": sum(isinstance(r, ArticleVersion) for r in records)},
        errors,
    )


def _retrieved_at(path: Path) -> datetime:
    """A downloaded dump is dated by its file: the dump itself does not say when."""
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _amendment_coverage(layer: Layer, count: int, ongoing: bool) -> LayerCoverage:
    stage = "committee" if layer == "committee_amendments" else "plenary"
    if count == 0:
        reason = f"No {stage} amendments for this procedure in the Parltrack dump"
        return LayerCoverage(layer=layer, status="missing", count=0, reason=reason)
    if ongoing:
        reason = "Procedure ongoing: the dump may predate later amendments"
        return LayerCoverage(layer=layer, status="partial", count=count, reason=reason)
    return LayerCoverage(layer=layer, status="complete", count=count)


def _amendments(run: _Run, dumps: Sequence[SourceDocument]) -> _Built:
    """Stage 2: committee and plenary amendments, and the MEPs who tabled them."""
    procedure = run.law.procedure_id
    skipped: Counter[str] = Counter()
    try:
        committee = tuple(
            parltrack.committee_amendments(
                run.inputs.committee_amendments, procedure, run.started_at, skipped
            )
        )
        plenary = tuple(
            parltrack.plenary_amendments(
                run.inputs.plenary_amendments, procedure, run.started_at, skipped
            )
        )
        mep_ids = sorted(
            {
                int(author.removeprefix(_MEP_PREFIX))
                for amendment in (*committee, *plenary)
                for author in amendment.author_ids
                if author.startswith(_MEP_PREFIX)
            }
        )
        meps = tuple(parltrack.mep_actors(run.inputs.meps, mep_ids, skipped))
    except ParltrackError as error:
        raise CollectError(f"A Parltrack dump is unreadable: {error}") from error
    law = run.law_record(
        [
            _amendment_coverage("committee_amendments", len(committee), run.ongoing),
            _amendment_coverage("plenary_amendments", len(plenary), run.ongoing),
        ]
    )
    counts = {"committee": len(committee), "plenary": len(plenary), "meps": len(meps)}
    counts |= {f"skipped_{reason}": number for reason, number in skipped.items()}
    return _Built(
        {
            "law.jsonl": (law,),
            "documents.jsonl": tuple(dumps),
            "amendments.jsonl": (*committee, *plenary),
            "actors.jsonl": meps,
        },
        counts,
    )


@dataclass
class _Asks:
    """What the asks stage gathers before it becomes records and coverage."""

    documents: list[SourceDocument] = field(default_factory=list[SourceDocument])
    texts: list[DocumentText] = field(default_factory=list[DocumentText])
    passages: list[Passage] = field(default_factory=list[Passage])
    actors: list[Actor] = field(default_factory=list[Actor])
    feedback: int = 0
    unread_publications: list[str] = field(default_factory=list[str])
    attachment_errors: list[str] = field(default_factory=list[str])
    attachments_unreadable: int = 0
    attachments_skipped: int = 0

    def problems(self) -> list[str]:
        """Why the layer is incomplete, one clause per kind of gap."""
        found = [
            (len(self.unread_publications), "publication(s) not served or not read"),
            (len(self.attachment_errors), "attachment(s) not downloaded"),
            (self.attachments_unreadable, "attachment(s) with no extractable text"),
            (self.attachments_skipped, "attachment(s) skipped by request"),
        ]
        return [f"{number} {what}" for number, what in found if number]

    def add(
        self, document: SourceDocument, text: DocumentText, passages: Iterable[Passage]
    ) -> None:
        self.documents.append(document)
        self.texts.append(text)
        self.passages.extend(passages)


def fetched_at(fetcher: CachedFetcher, url: str, fallback: datetime) -> datetime:
    """When the cached response for `url` was fetched; `fallback` when it is not cached."""
    cached = fetcher.cache.load(request_key("GET", url, b""))
    return fallback if cached is None else cached.metadata.fetched_at


def _initiatives(run: _Run, com: str, title: str) -> tuple[tuple[hys.IndexEntry, ...], str | None]:
    """Initiatives carrying the COM reference: from the index, else a labelled title search."""
    if run.inputs.hys_index.is_file():
        try:
            return hys.find_initiatives(hys.read_index(run.inputs.hys_index), com), None
        except hys.HysError as error:
            raise CollectError(f"The Have Your Say index is unreadable: {error}") from error
    note = "Initiative found by title search: the Have Your Say index is not built"
    try:
        return hys.find_by_title(run.fetcher, title, com), note
    except hys.HysError as error:
        return (), f"Have Your Say title search failed: {error}"


def _publication(run: _Run, publication_id: int, resolver: ActorResolver, found: _Asks) -> None:
    """Every feedback of one publication, with its attachments, passages and actor."""
    procedure = run.law.procedure_id
    try:
        items = tuple(hys.iter_feedback(run.fetcher, publication_id))
    except hys.HysError as error:
        found.unread_publications.append(str(error))
        return
    for position, item in enumerate(items):
        url = hys.feedback_url(publication_id, position // hys.PAGE_SIZE)
        retrieved = fetched_at(run.fetcher, url, run.started_at)
        document, text = hys.feedback_records(
            item, procedure_id=procedure, retrieved_at=retrieved, url=url
        )
        actor = resolver.resolve(
            item.organization,
            register_id=item.register_id,
            source_kind="hys_feedback",
            user_type=item.user_type,
            country=item.country,
            document_id=document.document_id,
        )
        found.feedback += 1
        found.actors.append(actor)
        found.add(document, text, _passages(procedure, actor, item, document, text))
        if not run.settings.attachments:
            found.attachments_skipped += len(item.attachments)
            continue
        for attachment in item.attachments:
            try:
                attached, attached_text = hys.fetch_attachment(
                    run.fetcher, attachment, item, procedure_id=procedure
                )
            except hys.HysError as error:
                found.attachment_errors.append(str(error))
                continue
            if attached_text is None:
                found.attachments_unreadable += 1
                found.documents.append(attached)
                continue
            found.add(
                attached,
                attached_text,
                _passages(procedure, actor, item, attached, attached_text),
            )


def _passages(
    procedure: str,
    actor: Actor,
    item: hys.FeedbackItem,
    document: SourceDocument,
    text: DocumentText,
) -> tuple[Passage, ...]:
    return document_passages(
        document,
        text,
        procedure_id=procedure,
        actor_id=actor.actor_id,
        submitted_at=item.submitted_at,
    )


def _asks_coverage(found: _Asks, note: str | None, com: str) -> LayerCoverage:
    problems = found.problems()
    reasons = [*problems, *([note] if note else [])]
    if found.feedback == 0:
        reason = "; ".join(reasons) or f"No feedback on the initiatives carrying {com}"
        return LayerCoverage(layer="asks", status="missing", count=0, reason=reason)
    return LayerCoverage(
        layer="asks",
        status="partial" if problems else "complete",
        count=found.feedback,
        reason="; ".join(reasons) or None,
    )


def _asks(run: _Run, com: str | None) -> _Built:
    """Stage 3: consultation feedback and attachments, split into passages, with actors."""
    if com is None:
        reason = "No COM reference is known, and Have Your Say is joined by COM reference only"
        law = run.law_record([LayerCoverage(layer="asks", status="missing", reason=reason)])
        return _Built(_files(_ASKS_FILES, law=law), {"feedback": 0})
    title = run.law.entry.title if run.law.entry else run.law.procedure_id
    initiatives, note = _initiatives(run, com, title)
    found = _Asks()
    if initiatives:
        try:
            resolver = ActorResolver.build(iter_register(run.inputs.register))
        except RegisterError as error:
            raise CollectError(f"The register export is unreadable: {error}") from error
        publications = sorted(
            {p.publication_id for initiative in initiatives for p in initiative.publications}
        )
        for publication_id in publications:
            _publication(run, publication_id, resolver, found)
    actors = merge_actors(found.actors)
    law = run.law_record([_asks_coverage(found, note, com)])
    counts = {
        "initiatives": len(initiatives),
        "feedback": found.feedback,
        "documents": len(found.documents),
        "passages": len(found.passages),
        "attachments_failed": len(found.attachment_errors),
        "attachments_unreadable": found.attachments_unreadable,
    } | {f"actors_{method}": n for method, n in resolution_summary(actors).items()}
    return _Built(
        {
            "law.jsonl": (law,),
            "documents.jsonl": tuple(found.documents),
            "document_texts.jsonl": tuple(found.texts),
            "passages.jsonl": tuple(found.passages),
            "actors.jsonl": actors,
        },
        counts,
        (*found.unread_publications, *found.attachment_errors),
    )


# --- The run --------------------------------------------------------------------------------


def _coverage(
    law: ResolvedLaw, stage_laws: Iterable[LawRecord], actors: int
) -> tuple[LayerCoverage, ...]:
    """One row per layer, in a fixed order: what the stages found, and what nobody tried."""
    rows = {item.layer: item for record in stage_laws for item in record.coverage}
    rows["metadata"] = (
        LayerCoverage(layer="metadata", status="complete", count=1)
        if law.entry is not None
        else LayerCoverage(
            layer="metadata",
            status="missing",
            reason="Not in the Parltrack dossiers dump: newer than the dump, or no procedure",
        )
    )
    rows["actors"] = (
        LayerCoverage(layer="actors", status="complete", count=actors)
        if actors
        else LayerCoverage(layer="actors", status="missing", count=0, reason="No actor is named")
    )
    for layer in ("meetings", "votes"):
        rows[layer] = LayerCoverage(layer=layer, status="not_collected", reason=NOT_BUILT_GAP)
    return tuple(rows[layer] for layer in LAYERS)


def collect_law(
    query: str,
    *,
    inputs: CollectInputs,
    settings: CollectSettings,
    fetcher: CachedFetcher,
    clock: Callable[[], datetime],
) -> CollectResult:
    """Resolve the query to one procedure and write its bundle under `data/laws/<slug>/`.

    Stops with `CollectError` when a required file is missing, the law cannot be
    identified, or the law has neither amendments nor submissions: there would be nothing
    to analyse, and an empty bundle must not look like a law nobody tried to influence.
    """
    absent = inputs.missing()
    if absent:
        listed = ", ".join(str(path) for path in absent)
        raise CollectError(f"Required input files are missing: {listed}")
    started_at = clock()
    catalog = load_catalog(inputs.dossiers, settings.data_root / "catalog")
    law = resolve_law(query, catalog, fetcher)
    bundle = settings.data_root / "laws" / procedure_slug(law.procedure_id)
    run = _Run(StageStore(bundle), fetcher, inputs, settings, law, started_at)
    procedure, revision = law.procedure_id, settings.code_revision

    texts = run.stage("texts", input_hash("texts", procedure, revision), lambda: _texts(run))
    (texts_law,) = run.store.read_output(texts, "law.jsonl", LawRecord)

    try:
        dumps = tuple(
            parltrack.dump_source_document(path, _retrieved_at(path))
            for path in (inputs.committee_amendments, inputs.plenary_amendments, inputs.meps)
        )
    except ParltrackError as error:
        raise CollectError(f"A Parltrack dump is unreadable: {error}") from error
    amendments = run.stage(
        "amendments",
        input_hash("amendments", procedure, revision, *(dump.sha256 for dump in dumps)),
        lambda: _amendments(run, dumps),
    )
    (amendments_law,) = run.store.read_output(amendments, "law.jsonl", LawRecord)

    com = texts_law.com_reference
    index = file_sha256(inputs.hys_index) if inputs.hys_index.is_file() else "no-index"
    asks = run.stage(
        "asks",
        input_hash(
            "asks",
            procedure,
            revision,
            com or "no-com",
            index,
            file_sha256(inputs.register),
            str(settings.attachments),
        ),
        lambda: _asks(run, com),
    )
    (asks_law,) = run.store.read_output(asks, "law.jsonl", LawRecord)

    actors = merge_actors(
        (
            *run.store.read_output(amendments, "actors.jsonl", Actor),
            *run.store.read_output(asks, "actors.jsonl", Actor),
        )
    )
    stage_laws = (texts_law, amendments_law, asks_law)
    record = run.law_record(
        _coverage(law, stage_laws, len(actors)),
        celex_proposal=texts_law.celex_proposal,
        celex_final=texts_law.celex_final,
        com_reference=texts_law.com_reference,
    )
    found = {item.layer: item.count or 0 for item in record.coverage}
    if found["committee_amendments"] + found["plenary_amendments"] + found["asks"] == 0:
        raise CollectError(
            f"{procedure} has no amendments and no consultation submissions to analyse"
        )
    run.stage(
        "law",
        input_hash("law", *(receipt.input_hash for receipt in run.receipts)),
        lambda: _Built({"laws.jsonl": (record,), "actors.jsonl": actors}, {"actors": len(actors)}),
    )
    manifest = RunManifest(
        run_id=f"{started_at:%Y%m%dT%H%M%SZ}",
        query=query,
        procedure_id=procedure,
        status="complete",
        started_at=started_at,
        completed_at=clock(),
        code_revision=revision,
        config={
            "attachments": "yes" if settings.attachments else "no",
            "refresh": "yes" if settings.refresh else "no",
        },
        hardware=settings.hardware,
        stages=tuple(run.receipts),
        coverage=record.coverage,
    )
    return CollectResult(record, manifest, run.store.publish(manifest), bundle)
