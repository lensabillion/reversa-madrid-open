"""Project published Atlas evidence without making new influence or outcome judgments."""

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import date, datetime

from influence.schemas.atlas import (
    Actor,
    Amendment,
    ArticleVersion,
    Ask,
    DocumentText,
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    LawRecord,
    LinkAssessment,
    NodeKind,
    Outcome,
    OutcomeResult,
    OutcomeStage,
    Passage,
    Relation,
    SourceDocument,
    SourceSpan,
    span_matches,
)


def _index[T](records: Sequence[T], key: Callable[[T], str]) -> dict[str, T]:
    result: dict[str, T] = {}
    for record in records:
        identifier = key(record)
        if identifier in result and result[identifier] != record:
            raise ValueError(f"Conflicting records for {identifier}")
        result[identifier] = record
    return result


def _get[T](records: dict[str, T], identifier: str) -> T:
    if identifier not in records:
        raise ValueError(f"Missing referenced record {identifier}")
    return records[identifier]


def build_graph(
    *,
    snapshot_id: str,
    run_id: str,
    generated_at: datetime,
    laws: Sequence[LawRecord],
    documents: Sequence[SourceDocument],
    document_texts: Sequence[DocumentText],
    actors: Sequence[Actor],
    passages: Sequence[Passage],
    asks: Sequence[Ask],
    amendments: Sequence[Amendment],
    articles: Sequence[ArticleVersion],
    links: Sequence[LinkAssessment],
    outcomes: Sequence[Outcome],
) -> GraphSnapshot:
    """Build one public snapshot; audit-only records never create nodes or edges.

    Designed for one law or a batch of cached laws. Indexing is O(R + Q), sorting
    O((N + E) log(N + E)), where R is input records, Q quoted characters and N/E output
    nodes/edges. The caller supplies timestamp and identity, so replay is deterministic.
    Exact duplicate IDs are idempotent; conflicting IDs and invalid published joins fail.
    Outcomes for unpublished asks remain inputs to analysis, not public influence paths.
    Missing outcomes produce no realization edge, never a fabricated loss.
    """
    law_by_id = _index(laws, lambda row: row.procedure_id)
    document_by_id = _index(documents, lambda row: row.document_id)
    texts = _index(document_texts, lambda row: row.document_id)
    actor_by_id = _index(actors, lambda row: row.actor_id)
    passage_by_id = _index(passages, lambda row: row.passage_id)
    ask_by_id = _index(asks, lambda row: row.ask_id)
    amendment_by_id = _index(amendments, lambda row: row.amendment_id)
    article_by_id = _index(articles, lambda row: row.article_id)
    link_by_id = _index(links, lambda row: row.link_id)
    outcome_by_id = _index(outcomes, lambda row: row.outcome_id)
    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}
    published: dict[str, LinkAssessment] = {}

    def node(identifier: str, kind: NodeKind, label: str) -> None:
        nodes[identifier] = GraphNode(
            node_id=identifier, kind=kind, label=label, record_id=identifier
        )

    def edge(
        relation: Relation,
        source: str,
        target: str,
        *,
        spans: tuple[SourceSpan, ...] = (),
        link_id: str | None = None,
        outcome_id: str | None = None,
        dated_on: date | None = None,
    ) -> None:
        identity = json.dumps((relation, source, target, link_id, outcome_id)).encode()
        identifier = f"edge:{hashlib.sha256(identity).hexdigest()}"
        edges[identifier] = GraphEdge(
            edge_id=identifier,
            relation=relation,
            source=source,
            target=target,
            spans=spans,
            link_id=link_id,
            outcome_id=outcome_id,
            dated_on=dated_on,
        )

    def document(identifier: str, procedure: str) -> None:
        source = _get(document_by_id, identifier)
        if source.procedure_id is not None and source.procedure_id != procedure:
            raise ValueError(f"Source {identifier} belongs to another procedure")

    def ask_quote(span: SourceSpan, ask: Ask) -> tuple[int, int]:
        # Normalize a passage-local quote to its document coordinate for containment.
        if span.field != "text":
            raise ValueError("Ask evidence must quote text")
        start, end = span.start, span.end
        if span.record_id == ask.document_id:
            text = _get(texts, ask.document_id).text
        elif span.record_id == ask.passage_id:
            passage = _get(passage_by_id, span.record_id)
            text = passage.span.text
            start += passage.span.start
            end += passage.span.start
        else:
            raise ValueError("Ask evidence quotes an unrelated source")
        if not span_matches(span, text):
            raise ValueError("Ask evidence does not match source text")
        return start, end

    for law in law_by_id.values():
        node(law.procedure_id, "procedure", law.title)

    for link in link_by_id.values():
        if link.status != "published":
            continue
        ask = _get(ask_by_id, link.ask_id)
        amendment = _get(amendment_by_id, link.amendment_id)
        _get(law_by_id, link.procedure_id)
        if ask.procedure_id != link.procedure_id or amendment.procedure_id != link.procedure_id:
            raise ValueError("Published link joins different procedures")
        document(ask.document_id, link.procedure_id)
        document(amendment.document_id, link.procedure_id)
        if (
            ask.submitted_at is None
            or amendment.tabled_on is None
            or ask.submitted_at.date() > amendment.tabled_on
        ):
            raise ValueError("Published link has inconsistent chronology")
        if ask.passage_id is not None:
            passage = _get(passage_by_id, ask.passage_id)
            if (
                passage.document_id != ask.document_id
                or passage.actor_id != ask.actor_id
                or passage.procedure_id != ask.procedure_id
                or passage.span.record_id != ask.document_id
                or passage.span.field != "text"
            ):
                raise ValueError("Ask passage has inconsistent ownership")
            ask_quote(passage.span, ask)
        start, end = ask_quote(ask.span, ask)
        for span in link.ask_spans:
            quote_start, quote_end = ask_quote(span, ask)
            if quote_start < start or quote_end > end:
                raise ValueError("Link quotation falls outside its ask")
        for span in link.amendment_spans:
            field = {
                "old_text": amendment.old_text,
                "new_text": amendment.new_text,
                "justification": amendment.justification,
            }.get(span.field)
            if (
                span.record_id != amendment.amendment_id
                or field is None
                or not span_matches(span, field)
            ):
                raise ValueError("Amendment evidence does not match its record")
        node(ask.ask_id, "ask", ask.requested_change or ask.span.text)
        for actor_id in {ask.actor_id, *ask.joint_actor_ids}:
            actor = _get(actor_by_id, actor_id)
            node(actor_id, "actor", actor.name)
            edge(
                "REQUESTED",
                actor_id,
                ask.ask_id,
                spans=(ask.span,),
                dated_on=ask.submitted_at.date(),
            )
        node(amendment.amendment_id, "amendment", amendment.amendment_id)
        edge(
            "ECHOED_BY",
            ask.ask_id,
            amendment.amendment_id,
            spans=link.ask_spans + link.amendment_spans,
            link_id=link.link_id,
            dated_on=amendment.tabled_on,
        )
        edge("ABOUT", amendment.amendment_id, link.procedure_id)
        for actor_id in amendment.author_ids:
            actor = _get(actor_by_id, actor_id)
            node(actor_id, "actor", actor.name)
            edge("TABLED_BY", amendment.amendment_id, actor_id, dated_on=amendment.tabled_on)
        published[link.link_id] = link

    published_asks = {link.ask_id for link in published.values()}
    published_pairs = {(link.ask_id, link.amendment_id) for link in published.values()}
    results: dict[tuple[str, OutcomeStage], OutcomeResult] = {}
    for outcome in outcome_by_id.values():
        if outcome.ask_id not in published_asks:
            continue
        result_key = (outcome.ask_id, outcome.stage)
        if result_key in results and results[result_key] != outcome.result:
            raise ValueError("Conflicting outcome results for the same ask and stage")
        results[result_key] = outcome.result
        ask = _get(ask_by_id, outcome.ask_id)
        if outcome.procedure_id != ask.procedure_id:
            raise ValueError("Outcome belongs to another procedure")
        if outcome.link_id is not None:
            link = _get(link_by_id, outcome.link_id)
            if link.ask_id != outcome.ask_id or link.amendment_id != outcome.amendment_id:
                raise ValueError("Outcome does not match its link")
        if outcome.relation == "via_amendment":
            if (outcome.ask_id, outcome.amendment_id) not in published_pairs:
                raise ValueError("Outcome references an unpublished amendment path")
            if outcome.link_id is not None and outcome.link_id not in published:
                raise ValueError("Outcome references an unpublished link")
        elif outcome.amendment_id is not None or outcome.link_id is not None:
            raise ValueError("Direct outcome must not claim an amendment path")
        if outcome.stage != "final_act" or outcome.result not in ("full", "partial"):
            continue
        if outcome.article_id is None:
            raise ValueError("Observed final outcome needs an article")
        article = _get(article_by_id, outcome.article_id)
        if article.stage != "final_act" or article.procedure_id != outcome.procedure_id:
            raise ValueError("Final outcome cites a different stage or procedure")
        document(article.document_id, outcome.procedure_id)
        for span in outcome.spans:
            if (
                span.record_id != article.article_id
                or span.field != "text"
                or not span_matches(span, article.text)
            ):
                raise ValueError("Outcome evidence does not match its article")
        node(article.article_id, "article", article.provision)
        edge(
            "REALIZED_IN",
            ask.ask_id,
            article.article_id,
            spans=outcome.spans,
            outcome_id=outcome.outcome_id,
            dated_on=article.version_date,
        )

    return GraphSnapshot(
        snapshot_id=snapshot_id,
        run_id=run_id,
        generated_at=generated_at,
        procedure_ids=tuple(sorted(law_by_id)),
        nodes=tuple(nodes[key] for key in sorted(nodes)),
        edges=tuple(edges[key] for key in sorted(edges)),
        coverage={key: law_by_id[key].coverage for key in sorted(law_by_id)},
    )
