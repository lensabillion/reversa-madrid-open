"""Parts 3 to 7 for one collected law, and the view the explorer reads (part 8).

This reads what `influence collect` wrote and runs each part's own code in order: asks from
passages, candidates by BM25 (`services/retrieval.py`), a verdict on every candidate
(`services/assessment.py`), outcomes for every ask that has a link it could have caused
(`services/outcomes.py`), the graph (`services/atlas_graph.py`) and descriptive outcome
counts (`services/atlas_analysis.py`). Nothing is scored, ranked or judged here.

The outcome counts take every ask, not only the shown ones, so their denominators are
complete: an ask without a traced outcome counts as unknown, never as a loss and never left
out. The rankings count outcomes traced through published links only (plan section 7): the
view keeps the outcomes traced through unconfirmed links for the audit view, but an ask
whose only links are unconfirmed is unknown in the rankings. Asks without a link are not
traced to the final act on their own wording, because that costs one alignment pass over
every final provision per ask: about 130 ms per ask against 712 provisions, measured on
3 October 2026, which is over an hour for the AI Act's 29,000 passages.

One stand-in remains until part 3's ask extraction exists: every consultation passage is
treated as one ask (`ASK_METHOD`). That is enough to find and quote links, but it makes
outcome counts count passages, not distinct requests, and the view says so.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import chain
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
    InvalidAtlasView,
    RankingRow,
)
from influence.schemas.retrieval import SourcePassage
from influence.services.assessment import (
    DEFAULT_PUBLISHABLE,
    METHOD_REVISION,
    ask_limit_reason,
    assess_link,
    requested_direction,
)
from influence.services.atlas_analysis import MIN_ASSESSED_ASKS, aggregate_outcomes
from influence.services.atlas_graph import build_graph
from influence.services.coordinated import CoordinationError, cross_group_clusters
from influence.services.masking import QuotedLaw
from influence.services.modes import mode_labels
from influence.services.outcomes import trace_outcomes
from influence.services.prose_match import rarity_weights
from influence.services.retrieval import PassageIndex

ASK_METHOD = "passage-v0"
CANDIDATES_PER_AMENDMENT = 5
VIEW_FILE = "atlas.json"
# Statuses the explorer shows: published links, and the audit view's unconfirmed and
# contradicted ones. `insufficient_evidence` verdicts stay out of the view.
SHOWN_STATUSES = frozenset({"published", "unconfirmed", "contradicted"})
# A link the ask could have caused, so the ask's outcome is traced through its amendment.
# Unconfirmed links are traced for the audit view only; the rankings use RANKED_STATUSES.
TRACED_STATUSES = frozenset({"published", "unconfirmed"})
RANKED_STATUSES = frozenset({"published"})
# Recall at 5 of the changed-words query on LobbyPlag's 172 verified pairs
# (`evaluation/retrieval-recall.json`), and of its union with a whole-text query
# (`evaluation/fused-retrieval.json`), which this pipeline does not run.
DELTA_RECALL_AT_5 = 0.82
UNION_RECALL_AT_5 = 0.965
LIMITATIONS = (
    "Ask extraction v0: each consultation passage is treated as one ask, so outcome counts "
    "count passages, not distinct requests.",
    # Built from part 4's own constants, so the sentence follows its revision and tiers.
    f"Links come from lexical rules ({METHOD_REVISION}); only "
    f"{' and '.join(sorted(DEFAULT_PUBLISHABLE))}-tier links are published, at provisional "
    "thresholds proposed from LobbyPlag's labelled pairs from one 2013 law and not yet "
    "frozen: the held-out Wilson lower bound of the copied threshold's precision (0.86) is "
    "below the 0.90 floor, and precision on this law has not been audited yet.",
    f"Retrieval keeps the top {CANDIDATES_PER_AMENDMENT} BM25 candidates per amendment, "
    "searched with the amendment's changed words only; on LobbyPlag that query finds "
    f"{DELTA_RECALL_AT_5:.0%} of verified pairs in its top {CANDIDATES_PER_AMENDMENT} "
    f"(adding a whole-text query would find {UNION_RECALL_AT_5:.1%} but is not run), so "
    "some true links are never assessed.",
    "Rankings count only outcomes traced through published links. Outcomes traced through "
    "unconfirmed links are kept for the audit view and never counted: an ask whose only "
    "links are unconfirmed, like an ask with no link, counts as unknown, not as a loss.",
    "One link is kept per amendment, actor, document and quoted ask span, so an instruction "
    "in the sentence two overlapping passages share is not shown twice. For counting, asks "
    "of one actor that request the same normalised text (a feedback text and its "
    "attachment, for example) count as one ask.",
    "Ask extraction v0 reads a direction only from quoted instructions (\"replace 'may' "
    "with 'shall'\"): prose asks have none, so part 4's direction checks do not run on them, "
    "and an ask to keep the proposal's text unchanged is never judged as a defence of the "
    "status quo.",
)
UNMASKED = (
    "The proposal's text is missing, so wording that submissions quote from it was not masked "
    "out of their shared-phrase matches."
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
    """One ask per passage, quoting the passage whole: the stand-in for ask extraction.

    The direction is read from the passage's quoted instructions (`requested_direction`),
    so part 4 can compare it with the amendment's; a prose passage's is unknown.
    """
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
            direction=requested_direction(passage.span.text),
            extraction_method=ASK_METHOD,
        )
        for passage in passages
    )


def find_candidates(
    amendments: Iterable[Amendment],
    asks: Sequence[Ask],
    unsearchable: list[str] | None = None,
    *,
    unsearchable_asks: dict[str, str] | None = None,
) -> tuple[Candidate, ...]:
    """The top BM25 asks for each amendment's changed words.

    An amendment the scorer's bounds refuse (over 800 tokens a side, as a long recital can
    be, or no text), or whose change leaves no word to search (case or punctuation only),
    has no candidates; its ID is appended to `unsearchable` so the view can say so, instead
    of one long amendment stopping a whole law.

    Unsupported asks are excluded before indexing so they cannot consume the shortlist.
    Their IDs/reasons are recorded in unsearchable_asks, never their truncated replacements.

    Building the index is linear in the asks' total length; each search costs the postings
    of the amendment's distinct changed words plus O(M log k) over M matching passages.
    """
    searchable: list[Ask] = []
    for ask in asks:
        if reason := ask_limit_reason(ask):
            if unsearchable_asks is not None:
                unsearchable_asks[ask.ask_id] = reason
        else:
            searchable.append(ask)
    index = PassageIndex(
        tuple(
            SourcePassage(
                document_id=ask.document_id,
                start=ask.span.start,
                end=ask.span.end,
                text=ask.span.text,
            )
            for ask in searchable
        )
    )
    by_slice = {(ask.document_id, ask.span.start, ask.span.end): ask for ask in searchable}
    found: list[Candidate] = []
    for amendment in amendments:
        try:
            shortlist = index.search(
                amendment.amendment_id,
                amendment.old_text,
                amendment.new_text,
                k=CANDIDATES_PER_AMENDMENT,
            )
        except ValueError:
            if unsearchable is not None:
                unsearchable.append(amendment.amendment_id)
            continue
        if not shortlist.query_terms:
            # A change of case or punctuation only leaves no word to search for.
            if unsearchable is not None:
                unsearchable.append(amendment.amendment_id)
            continue
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
    background: Iterable[str] = (),
    publish_prose: bool = False,
    *,
    quoted_law: QuotedLaw | None,
) -> tuple[LinkAssessment, ...]:
    """Part 4's verdict on every candidate, quoting the ask against its document's text.

    Word rarity is measured over the law's own passages and its provisions (`background`),
    so a phrase every submission or the Act itself uses ("placed on the market") counts for
    little against one that only a few use. `quoted_law` is the proposal's wording, masked
    out of prose before shared phrases are found; it is required so that a caller cannot
    skip masking by omission, and None only when the proposal's text is missing.
    """
    rarity = rarity_weights(chain((ask.span.text for ask in asks.values()), background))
    verdicts: list[LinkAssessment] = []
    for candidate in candidates:
        ask = asks[candidate.ask_id]
        verdicts.append(
            assess_link(
                amendments[candidate.amendment_id],
                ask,
                texts[ask.document_id],
                candidate_id=candidate.candidate_id,
                rarity=rarity,
                publish_prose=publish_prose,
                quoted_law=quoted_law,
            )
        )
    return tuple(verdicts)


def origin_links(links: Iterable[LinkAssessment]) -> dict[str, LinkAssessment]:
    """Each ask's strongest link it could have caused: published first, then by score.

    Only a link whose ask came first can be the ask's origin, so eligibility is checked
    before strength: a stronger link to an earlier amendment must not hide a weaker one the
    ask could have caused.
    """
    origins: dict[str, LinkAssessment] = {}
    for link in sorted(
        (
            link
            for link in links
            if link.status in TRACED_STATUSES and link.time_eligibility == "ask_first"
        ),
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
    """Outcomes for every ask with a published or unconfirmed link.

    The ask is traced through its origin amendment when one came after it, and otherwise
    directly against the final act on its own wording. Asks with no such link are not
    traced (see the module docstring); the outcome counts treat them as unknown.
    """
    links = tuple(links)
    origins = origin_links(links)
    linked = {link.ask_id for link in links if link.status in TRACED_STATUSES}
    outcomes: list[Outcome] = []
    for ask in asks:
        if ask.ask_id not in linked:
            continue
        link = origins.get(ask.ask_id)
        amendment = amendments[link.amendment_id] if link is not None else None
        outcomes.extend(trace_outcomes(ask, amendment, link, articles))
    return tuple(outcomes)


def _strength(link: LinkAssessment) -> tuple[bool, bool, float, str]:
    return (
        link.status != "published",
        link.status != "unconfirmed",
        -link.support_score,
        link.link_id,
    )


def deduplicate_links(
    links: Iterable[LinkAssessment], asks: Mapping[str, Ask]
) -> tuple[LinkAssessment, ...]:
    """One link per amendment, actor, document and quoted ask span: the strongest, in order.

    Consultation passages overlap by one sentence (`services/passages.py`), so an
    instruction in the shared sentence is quoted at the same absolute offsets from two asks
    and would be shown, and counted, twice. A link that quotes no ask span is kept as it is.
    O(L log L) in the links.
    """
    links = tuple(links)
    kept: dict[tuple[object, ...], str] = {}
    for link in sorted(links, key=_strength):
        ask = asks[link.ask_id]
        quoted = tuple((span.record_id, span.start, span.end) for span in link.ask_spans)
        key = (link.amendment_id, ask.actor_id, ask.joint_actor_ids, ask.document_id, quoted)
        kept.setdefault(key if quoted else (link.link_id,), link.link_id)
    chosen = set(kept.values())
    return tuple(link for link in links if link.link_id in chosen)


def ranked_outcomes(
    links: Iterable[LinkAssessment], outcomes: Iterable[Outcome]
) -> tuple[Outcome, ...]:
    """The outcomes the rankings may count: those of asks with a published link.

    `outcomes` are the view's, traced through published and unconfirmed links. A published
    link is always ask-first (`LinkAssessment` refuses any other) and `origin_links` takes
    published links first, so an ask with one was traced through a published link and its
    outcomes are kept unchanged; an ask with only unconfirmed links loses its outcomes and
    counts as unknown. Linear in the links and outcomes.
    """
    ranked = {link.ask_id for link in links if link.status in RANKED_STATUSES}
    return tuple(outcome for outcome in outcomes if outcome.ask_id in ranked)


def _normalised(text: str) -> str:
    return " ".join(text.casefold().split())


def counted_asks(
    asks: Sequence[Ask], links: Iterable[LinkAssessment], outcomes: Sequence[Outcome]
) -> tuple[tuple[Ask, ...], tuple[Outcome, ...]]:
    """One ask per actor (with its co-signers) and normalised requested text, for counting.

    The requested text is what the ask's published origin link quotes, or else the ask's
    own passage, so a feedback text and its attachment that ask for the same wording count
    once (plan section 7). The ask kept is the first by ID that has a ranked outcome, so a
    repeat never hides an assessed outcome; the others' outcomes are not counted. Linear in
    the asks and outcomes apart from sorting each group.
    """
    origins = origin_links(link for link in links if link.status in RANKED_STATUSES)
    traced = {outcome.ask_id for outcome in outcomes}
    groups: dict[tuple[str, tuple[str, ...], str], list[Ask]] = defaultdict(list)
    for ask in asks:
        origin = origins.get(ask.ask_id)
        quoted = (
            " ".join(span.text for span in origin.ask_spans)
            if origin is not None and origin.ask_spans
            else ask.span.text
        )
        groups[(ask.actor_id, tuple(sorted(ask.joint_actor_ids)), _normalised(quoted))].append(ask)
    kept: set[str] = set()
    for members in groups.values():
        ordered = sorted(members, key=lambda ask: ask.ask_id)
        kept.add(next((a.ask_id for a in ordered if a.ask_id in traced), ordered[0].ask_id))
    return (
        tuple(ask for ask in asks if ask.ask_id in kept),
        tuple(outcome for outcome in outcomes if outcome.ask_id in kept),
    )


def _rankings(
    law: LawRecord,
    actors: Sequence[Actor],
    asks: Sequence[Ask],
    links: Sequence[LinkAssessment],
    outcomes: Sequence[Outcome],
) -> tuple[tuple[RankingRow, ...], tuple[str, ...]]:
    """Final-act rows over every ask, and the sentences that qualify them.

    `outcomes` must be traced through published links only (`ranked_outcomes`). The
    sentences say how many asks the rows count and how many of those are unknown, how many
    repeats and unconfirmed-only asks were set aside, and repeat each final-act coverage gap
    the analysis found, so a reader of the rankings sees why the counts may be incomplete.
    """
    counted, counted_outcomes = counted_asks(asks, links, outcomes)
    ranked = {link.ask_id for link in links if link.status in RANKED_STATUSES}
    unconfirmed_only = {
        link.ask_id
        for link in links
        if link.status in TRACED_STATUSES and link.ask_id not in ranked
    }
    # The asks layer counts feedback items, but passage-v0 asks are passages: comparing the
    # two would report a mismatch on every law, so the check waits for real ask extraction.
    analysis = aggregate_outcomes(
        laws=(law,),
        actors=actors,
        asks=counted,
        outcomes=counted_outcomes,
        ask_inventory=False,
    )
    (total,) = (counts for counts in analysis.totals if counts.stage == "final_act")
    prefix = "final_act: "
    repeats = len(asks) - len(counted)
    notes = (
        f"Final-act outcome counts cover all {total.observed_asks} ask(s): "
        f"{total.assessed_asks} assessed and {total.unknown} unknown.",
        *(
            (
                f"{repeats} ask(s) repeat another ask of the same actor with the same "
                "requested text and are counted once.",
            )
            if repeats
            else ()
        ),
        *(
            (
                f"{len(unconfirmed_only)} ask(s) have only unconfirmed links and count as "
                "unknown in the rankings until a link is published.",
            )
            if unconfirmed_only
            else ()
        ),
        f"Actors with fewer than {MIN_ASSESSED_ASKS} assessed asks are listed after the "
        "rest, whatever their rate, so a '1 of 1' cannot lead the ranking.",
        *(
            f"Final-act counts may be incomplete: {gap.removeprefix(prefix)}"
            for gap in analysis.coverage_gaps
            if gap.startswith(prefix)
        ),
    )
    rows = tuple(
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
    return rows, notes


def build_view(
    collected: Collected, *, generated_at: datetime, publish_prose: bool = False
) -> AtlasView:
    """Run parts 3 to 7 and keep every record the shown links reach, and only those.

    The graph and the bundle are built from the same records, so the frontend adapter
    re-checks exactly what the graph shows. Records that do not fit together (a record
    that fails validation, conflicting outcomes) raise PipelineError, so the command can
    keep the collected bundle and say why instead of stopping on a traceback.
    """
    try:
        return _view(collected, generated_at=generated_at, publish_prose=publish_prose)
    except ValueError as error:
        raise PipelineError(f"The view cannot be built from this run: {error}") from error


def _view(collected: Collected, *, generated_at: datetime, publish_prose: bool) -> AtlasView:
    law = collected.law
    asks = asks_from_passages(collected.passages)
    amendments = {amendment.amendment_id: amendment for amendment in collected.amendments}
    asks_by_id = {ask.ask_id: ask for ask in asks}
    texts = {text.document_id: text.text for text in collected.document_texts}
    unsearchable: list[str] = []
    unsearchable_asks: dict[str, str] = {}
    proposal = tuple(article.text for article in collected.articles if article.stage == "proposal")
    quoted_law = QuotedLaw(proposal) if proposal else None
    links = assess_candidates(
        find_candidates(
            collected.amendments, asks, unsearchable, unsearchable_asks=unsearchable_asks
        ),
        amendments,
        asks_by_id,
        texts,
        (article.text for article in collected.articles),
        publish_prose,
        quoted_law=quoted_law,
    )
    shown = deduplicate_links((link for link in links if link.status in SHOWN_STATUSES), asks_by_id)
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
    # Every ask and every actor, not the shown subset: counting only shown asks would leave
    # out the asks nobody matched and overstate each actor's win rate. Only outcomes traced
    # through published links are counted.
    rankings, ranking_notes = _rankings(
        law,
        collected.actors,
        asks,
        shown,
        ranked_outcomes(shown, outcomes),
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
        modes=mode_labels(law),
        bundle=bundle,
        snapshot=snapshot,
        rankings=rankings,
        limitations=(
            *LIMITATIONS,
            *((UNMASKED,) if quoted_law is None else ()),
            *ranking_notes,
            *(
                (
                    f"{len(unsearchable)} amendment(s) were too long or empty to search, or "
                    "changed only case or punctuation, and have no candidates.",
                )
                if unsearchable
                else ()
            ),
            *(
                (
                    f"{len(unsearchable_asks)} ask(s) could not be assessed and were excluded "
                    "before retrieval; original records retained in the collected bundle. "
                    + "; ".join(
                        f"{identifier}: {reason}"
                        for identifier, reason in sorted(unsearchable_asks.items())
                    ),
                )
                if unsearchable_asks
                else ()
            ),
        ),
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


def remove_stale_view(bundle: Path, run_id: str) -> bool:
    """Remove the bundle's view unless it was built from `run_id`; True when one was removed.

    Called when building a view fails after a collect run: the old view would otherwise
    keep being served, and read by `directions`, beside the newer run's records. A view
    that cannot be read is removed too; a view of this same run is kept.
    """
    path = bundle / VIEW_FILE
    if not path.is_file():
        return False
    try:
        current = _load_view(path).run_id == run_id
    except PipelineError:
        current = False
    if current:
        return False
    path.unlink()
    return True


def list_views(data_root: Path) -> AtlasLawList:
    """Every law with a valid written view, newest procedure first.

    A view that cannot be read is listed under `invalid` with its reason instead of
    failing the whole list, so one broken law does not hide every other.
    """
    laws: list[AtlasLawSummary] = []
    invalid: list[InvalidAtlasView] = []
    for path in sorted((data_root / "laws").glob(f"*/{VIEW_FILE}"), reverse=True):
        try:
            view = _load_view(path)
        except PipelineError as error:
            invalid.append(InvalidAtlasView(slug=path.parent.name, reason=str(error)))
            continue
        try:
            clusters = cross_group_clusters(data_root, view.slug)
        except CoordinationError as error:
            # The law's view is fine; only its cluster count is unknown, and says why.
            clusters = None
            invalid.append(InvalidAtlasView(slug=view.slug, reason=str(error)))
        laws.append(
            AtlasLawSummary(
                slug=view.slug,
                procedure_id=view.procedure_id,
                title=view.title,
                run_id=view.run_id,
                published_links=sum(link.status == "published" for link in view.bundle.links),
                cross_group_clusters=clusters,
            )
        )
    return AtlasLawList(laws=tuple(laws), invalid=tuple(invalid))
