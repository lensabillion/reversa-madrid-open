"""Parts 3 to 7 for one collected law, and the view the explorer reads (part 8).

This reads what `influence collect` wrote and runs each part's own code in order: asks from
passages, candidates by BM25 (`services/retrieval.py`), a verdict on every candidate
(`services/assessment.py`), outcomes for every ask that has a link it could have caused
(`services/outcomes.py`), the graph (`services/atlas_graph.py`) and descriptive outcome
counts (`services/atlas_analysis.py`). Nothing is scored, ranked or judged here.

One stand-in remains until part 3's ask extraction exists: every consultation passage is
treated as one ask (`ASK_METHOD`). That is enough to find and quote links, but it makes
outcome counts count passages, not distinct requests, and the view says so.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import procedure_slug
from influence.extraction.records import StageStore
from influence.schemas.atlas import (
    Actor,
    Amendment,
    ArticleVersion,
    Ask,
    AtlasRecord,
    Candidate,
    DocumentText,
    LawRecord,
    LinkAssessment,
    Outcome,
    Passage,
    RunManifest,
    SourceDocument,
    id_part,
)
from influence.schemas.atlas_view import (
    AtlasBundleView,
    AtlasLawList,
    AtlasLawSummary,
    AtlasView,
    RankingRow,
)
from influence.schemas.retrieval import SourcePassage
from influence.schemas.scoring import MAX_TEXT_LENGTH, MAX_TOKENS, TextChange
from influence.services.assessment import assess_link
from influence.services.atlas_analysis import aggregate_outcomes
from influence.services.atlas_graph import build_graph
from influence.services.outcomes import trace_outcomes
from influence.services.retrieval import PassageIndex

ASK_METHOD = "passage-v0"
CANDIDATES_PER_AMENDMENT = 5
VIEW_FILE = "atlas.json"
# Statuses the explorer shows: published links, and the audit view's unconfirmed and
# contradicted ones. `insufficient_evidence` verdicts stay out of the view.
SHOWN_STATUSES = frozenset({"published", "unconfirmed", "contradicted"})
# A link the ask could have caused, so the ask's outcome is traced through its amendment.
TRACED_STATUSES = frozenset({"published", "unconfirmed"})
LIMITATIONS = (
    "Ask extraction v0: each consultation passage is treated as one ask, so outcome counts "
    "count passages, not distinct requests.",
    "Links come from lexical rules (rules-1) with placeholder thresholds; their precision "
    "has not been audited yet.",
    "Outcomes are traced only for asks with a published or unconfirmed link.",
)


class PipelineError(RuntimeError):
    """The law has no completed collect run to build on, or its records do not fit."""


@dataclass(frozen=True)
class Collected:
    """The records one completed collect run wrote, read back from its bundle."""

    manifest: RunManifest
    law: LawRecord
    documents: tuple[SourceDocument, ...]
    document_texts: tuple[DocumentText, ...]
    passages: tuple[Passage, ...]
    actors: tuple[Actor, ...]
    amendments: tuple[Amendment, ...]
    articles: tuple[ArticleVersion, ...]


def load_collected(bundle: Path) -> Collected:
    """Read the current manifest's stage outputs; every line is validated on the way in."""
    store = StageStore(bundle)
    manifest = store.current()
    if manifest is None:
        raise PipelineError(f"No completed collect run in {bundle}")
    receipts = {receipt.stage: receipt for receipt in manifest.stages}
    missing = {"texts", "amendments", "asks", "law"} - receipts.keys()
    if missing:
        raise PipelineError(f"The collect run in {bundle} lacks stages {sorted(missing)}")

    def read[T: AtlasRecord](stage: str, name: str, model: type[T]) -> tuple[T, ...]:
        return store.read_output(receipts[stage], name, model)

    laws = read("law", "laws.jsonl", LawRecord)
    if len(laws) != 1:
        raise PipelineError(f"The collect run in {bundle} holds {len(laws)} laws, not one")
    return Collected(
        manifest=manifest,
        law=laws[0],
        documents=(
            *read("texts", "documents.jsonl", SourceDocument),
            *read("amendments", "documents.jsonl", SourceDocument),
            *read("asks", "documents.jsonl", SourceDocument),
        ),
        document_texts=(
            *read("texts", "document_texts.jsonl", DocumentText),
            *read("asks", "document_texts.jsonl", DocumentText),
        ),
        passages=read("asks", "passages.jsonl", Passage),
        actors=read("law", "actors.jsonl", Actor),
        amendments=read("amendments", "amendments.jsonl", Amendment),
        articles=read("texts", "articles.jsonl", ArticleVersion),
    )


def asks_from_passages(passages: Iterable[Passage]) -> tuple[Ask, ...]:
    """One ask per passage, quoting the passage whole: the stand-in for ask extraction."""
    return tuple(
        Ask(
            ask_id=f"ask:{id_part(passage.passage_id)}",
            procedure_id=passage.procedure_id,
            actor_id=passage.actor_id,
            document_id=passage.document_id,
            passage_id=passage.passage_id,
            span=passage.span,
            submitted_at=passage.submitted_at,
            language=passage.language,
            extraction_method=ASK_METHOD,
        )
        for passage in passages
    )


def comparable(amendment: Amendment) -> bool:
    """Whether the comparison's size limits admit this amendment's wording.

    The token diff behind retrieval, assessment and outcomes is quadratic and bounded by
    `TextChange`; a few real amendments replace a whole long recital or annex and exceed it.
    """
    try:
        TextChange(old=amendment.old_text or "", new=amendment.new_text)
    except ValidationError:
        return False
    return True


def find_candidates(amendments: Iterable[Amendment], asks: Sequence[Ask]) -> tuple[Candidate, ...]:
    """The top BM25 asks for each amendment's changed words.

    Building the index is linear in the asks' total length; each search costs the postings
    of the amendment's distinct changed words plus O(M log k) over M matching passages.
    """
    index = PassageIndex(
        tuple(
            SourcePassage(
                document_id=ask.document_id,
                start=ask.span.start,
                end=ask.span.end,
                text=ask.span.text,
            )
            for ask in asks
        )
    )
    by_slice = {(ask.document_id, ask.span.start, ask.span.end): ask for ask in asks}
    found: list[Candidate] = []
    for amendment in amendments:
        shortlist = index.search(
            amendment.amendment_id,
            amendment.old_text,
            amendment.new_text,
            k=CANDIDATES_PER_AMENDMENT,
        )
        for candidate in shortlist.candidates:
            passage = candidate.passage
            ask = by_slice[(passage.document_id, passage.start, passage.end)]
            found.append(
                Candidate(
                    candidate_id=f"cand:{id_part(amendment.amendment_id)}:{id_part(ask.ask_id)}",
                    procedure_id=amendment.procedure_id,
                    amendment_id=amendment.amendment_id,
                    ask_id=ask.ask_id,
                    lexical_rank=candidate.rank,
                    retrieval_score=candidate.score,
                    method=shortlist.method,
                )
            )
    return tuple(found)


def assess_candidates(
    candidates: Iterable[Candidate],
    amendments: Mapping[str, Amendment],
    asks: Mapping[str, Ask],
    texts: Mapping[str, str],
) -> tuple[LinkAssessment, ...]:
    """Part 4's verdict on every candidate, quoting the ask against its document's text."""
    verdicts: list[LinkAssessment] = []
    for candidate in candidates:
        ask = asks[candidate.ask_id]
        verdicts.append(
            assess_link(
                amendments[candidate.amendment_id],
                ask,
                texts[ask.document_id],
                candidate_id=candidate.candidate_id,
            )
        )
    return tuple(verdicts)


def origin_links(links: Iterable[LinkAssessment]) -> dict[str, LinkAssessment]:
    """Each ask's strongest link it could have caused: published first, then by score."""
    origins: dict[str, LinkAssessment] = {}
    for link in sorted(
        (link for link in links if link.status in TRACED_STATUSES),
        key=lambda link: (link.status != "published", -link.support_score, link.link_id),
    ):
        origins.setdefault(link.ask_id, link)
    return origins


def trace(
    asks: Iterable[Ask],
    amendments: Mapping[str, Amendment],
    links: Iterable[LinkAssessment],
    articles: Sequence[ArticleVersion],
) -> tuple[Outcome, ...]:
    """Outcomes for every ask with a link it could have caused, through that amendment."""
    origins = origin_links(links)
    outcomes: list[Outcome] = []
    for ask in asks:
        link = origins.get(ask.ask_id)
        if link is not None:
            outcomes.extend(trace_outcomes(ask, amendments[link.amendment_id], link, articles))
    return tuple(outcomes)


def _rankings(
    law: LawRecord, actors: Sequence[Actor], asks: Sequence[Ask], outcomes: Sequence[Outcome]
) -> tuple[RankingRow, ...]:
    analysis = aggregate_outcomes(laws=(law,), actors=actors, asks=asks, outcomes=outcomes)
    return tuple(
        RankingRow(
            actor_id=row.actor_id,
            actor_name=row.actor_name,
            observed_asks=row.counts.observed_asks,
            assessed_asks=row.counts.assessed_asks,
            full=row.counts.full,
            partial=row.counts.partial,
            not_observed=row.counts.not_observed,
            unknown=row.counts.unknown,
            full_win_rate=row.counts.full_win_rate,
            evidence_record_ids=row.evidence_record_ids,
        )
        for row in analysis.rows
        if row.counts.stage == "final_act"
    )


def build_view(collected: Collected, *, generated_at: datetime) -> AtlasView:
    """Run parts 3 to 7 and keep every record the shown links reach, and only those.

    The graph and the bundle are built from the same records, so the frontend adapter
    re-checks exactly what the graph shows.
    """
    law = collected.law
    asks = asks_from_passages(collected.passages)
    amendments = {amendment.amendment_id: amendment for amendment in collected.amendments}
    asks_by_id = {ask.ask_id: ask for ask in asks}
    texts = {text.document_id: text.text for text in collected.document_texts}
    # An amendment the comparison cannot hold is left out and counted, never a crash and
    # never a silent skip: the view's limitations say how many.
    analysed = tuple(amendment for amendment in collected.amendments if comparable(amendment))
    left_out = len(collected.amendments) - len(analysed)
    limitations = LIMITATIONS
    if left_out:
        limitations = (
            *LIMITATIONS,
            f"{left_out} of {len(collected.amendments)} amendments were not analysed: their "
            f"text is empty or exceeds the comparison limit of {MAX_TOKENS} tokens or "
            f"{MAX_TEXT_LENGTH} characters.",
        )
    links = assess_candidates(find_candidates(analysed, asks), amendments, asks_by_id, texts)
    shown = tuple(link for link in links if link.status in SHOWN_STATUSES)
    outcomes = trace(asks, amendments, shown, collected.articles)

    ask_ids = {link.ask_id for link in shown}
    shown_asks = tuple(ask for ask in asks if ask.ask_id in ask_ids)
    passage_ids = {ask.passage_id for ask in shown_asks}
    shown_amendments = tuple(amendments[i] for i in sorted({link.amendment_id for link in shown}))
    article_ids = {outcome.article_id for outcome in outcomes if outcome.article_id is not None}
    shown_articles = tuple(a for a in collected.articles if a.article_id in article_ids)
    document_ids = (
        {ask.document_id for ask in shown_asks}
        | {amendment.document_id for amendment in shown_amendments}
        | {article.document_id for article in shown_articles}
    )
    actor_ids = (
        {ask.actor_id for ask in shown_asks}
        | {actor for ask in shown_asks for actor in ask.joint_actor_ids}
        | {author for amendment in shown_amendments for author in amendment.author_ids}
    )
    bundle = AtlasBundleView(
        laws=(law,),
        documents=tuple(d for d in collected.documents if d.document_id in document_ids),
        document_texts=tuple(t for t in collected.document_texts if t.document_id in document_ids),
        passages=tuple(p for p in collected.passages if p.passage_id in passage_ids),
        actors=tuple(a for a in collected.actors if a.actor_id in actor_ids),
        asks=shown_asks,
        amendments=shown_amendments,
        articles=shown_articles,
        links=shown,
        outcomes=outcomes,
    )
    run_id = collected.manifest.run_id
    try:
        snapshot = build_graph(
            snapshot_id=f"snapshot:{procedure_slug(law.procedure_id)}:{run_id}",
            run_id=run_id,
            generated_at=generated_at,
            laws=bundle.laws,
            documents=bundle.documents,
            document_texts=bundle.document_texts,
            actors=bundle.actors,
            passages=bundle.passages,
            asks=bundle.asks,
            amendments=bundle.amendments,
            articles=bundle.articles,
            links=bundle.links,
            outcomes=bundle.outcomes,
        )
    except ValueError as error:
        raise PipelineError(f"The graph cannot be built from this run: {error}") from error
    return AtlasView(
        procedure_id=law.procedure_id,
        slug=procedure_slug(law.procedure_id),
        title=law.title,
        run_id=run_id,
        generated_at=generated_at,
        ask_method=ASK_METHOD,
        coverage=law.coverage,
        bundle=bundle,
        snapshot=snapshot,
        rankings=_rankings(law, bundle.actors, bundle.asks, bundle.outcomes),
        limitations=limitations,
    )


def write_view(view: AtlasView, bundle: Path) -> Path:
    path = bundle / VIEW_FILE
    write_bytes_atomic(path, view.model_dump_json(by_alias=True).encode("utf-8"))
    return path


def _load_view(path: Path) -> AtlasView:
    try:
        return AtlasView.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise PipelineError(f"The view at {path} is invalid: {error}") from error


def read_view(data_root: Path, slug: str) -> AtlasView | None:
    """The law's last written view, or None when that law has none."""
    path = data_root / "laws" / slug / VIEW_FILE
    return _load_view(path) if path.is_file() else None


def list_views(data_root: Path) -> AtlasLawList:
    """Every law with a written view, newest procedure first."""
    views = (
        _load_view(path)
        for path in sorted((data_root / "laws").glob(f"*/{VIEW_FILE}"), reverse=True)
    )
    return AtlasLawList(
        laws=tuple(
            AtlasLawSummary(
                slug=view.slug,
                procedure_id=view.procedure_id,
                title=view.title,
                run_id=view.run_id,
                published_links=sum(link.status == "published" for link in view.bundle.links),
            )
            for view in views
        )
    )
