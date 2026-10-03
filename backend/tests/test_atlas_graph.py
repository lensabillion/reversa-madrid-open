"""Graph consumer tests use invented upstream records, never accuracy labels."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from atlas_fixture import AtlasFixture, build_fixture

from influence.schemas.atlas import AtlasRecord, GraphSnapshot
from influence.services.atlas_graph import build_graph


def graph(fixture: AtlasFixture) -> GraphSnapshot:
    return build_graph(
        snapshot_id="snapshot:test",
        run_id="run:test",
        generated_at=datetime(2026, 10, 3, tzinfo=UTC),
        laws=fixture.laws,
        documents=fixture.documents,
        document_texts=fixture.document_texts,
        actors=fixture.actors,
        passages=fixture.passages,
        asks=fixture.asks,
        amendments=fixture.amendments,
        articles=fixture.articles,
        links=fixture.links,
        outcomes=fixture.outcomes,
    )


def test_fixture_paths_keep_only_published_links_and_unknown_final() -> None:
    fixture = build_fixture()
    snapshot = graph(fixture)
    assert {edge.link_id for edge in snapshot.edges if edge.relation == "ECHOED_BY"} == {
        "link:a-am1-makers",
        "link:b-am3-labels",
    }
    assert {edge.outcome_id for edge in snapshot.edges if edge.relation == "REALIZED_IN"} == {
        "outcome:a-ask-makers-final",
    }
    assert snapshot.coverage == {law.procedure_id: law.coverage for law in fixture.laws}


def changed[T: AtlasRecord](record: T, **updates: object) -> T:
    return type(record).model_validate({**record.model_dump(), **updates})


FIXTURE = build_fixture()
ASK = FIXTURE.asks[0]
LINK = FIXTURE.links[0]
FINAL = next(row for row in FIXTURE.outcomes if row.outcome_id == "outcome:a-ask-makers-final")
ARTICLE = next(row for row in FIXTURE.articles if row.article_id == FINAL.article_id)


def with_ask(**updates: object) -> AtlasFixture:
    return replace(FIXTURE, asks=(changed(ASK, **updates), *FIXTURE.asks[1:]))


def with_link(**updates: object) -> AtlasFixture:
    return replace(FIXTURE, links=(changed(LINK, **updates), *FIXTURE.links[1:]))


def with_outcome(**updates: object) -> AtlasFixture:
    return replace(FIXTURE, outcomes=(changed(FINAL, **updates),))


@pytest.mark.parametrize(
    ("fixture", "message"),
    [
        (
            replace(FIXTURE, asks=(*FIXTURE.asks, changed(ASK, requested_change="Different"))),
            "Conflicting",
        ),
        (replace(FIXTURE, actors=()), "Missing referenced"),
        (with_link(ask_id="ask:absent"), "Missing referenced"),
        (with_ask(procedure_id=FIXTURE.laws[1].procedure_id), "different procedures"),
        (with_ask(submitted_at=None), "chronology"),
        (with_ask(submitted_at=datetime(2100, 1, 1, tzinfo=UTC)), "chronology"),
        (with_ask(passage_id=FIXTURE.passages[1].passage_id), "passage has inconsistent"),
        (
            with_link(ask_spans=(LINK.ask_spans[0].model_copy(update={"field": "old_text"}),)),
            "quote text",
        ),
        (
            with_link(
                ask_spans=(
                    LINK.ask_spans[0].model_copy(update={"record_id": "doc:hys_feedback:other"}),
                )
            ),
            "unrelated source",
        ),
        (
            with_link(
                ask_spans=(
                    LINK.ask_spans[0].model_copy(
                        update={"text": "X" * len(LINK.ask_spans[0].text)}
                    ),
                )
            ),
            "match source text",
        ),
        (
            with_ask(
                span=LINK.ask_spans[0].model_copy(
                    update={"start": 98, "text": LINK.ask_spans[0].text[1:]}
                )
            ),
            "outside its ask",
        ),
        (
            with_link(
                amendment_spans=(LINK.amendment_spans[0].model_copy(update={"field": "text"}),)
            ),
            "Amendment evidence",
        ),
        (with_outcome(procedure_id=FIXTURE.laws[1].procedure_id), "another procedure"),
        (with_outcome(link_id=FIXTURE.links[1].link_id), "does not match its link"),
        (
            with_outcome(link_id=None, amendment_id=FIXTURE.amendments[1].amendment_id),
            "unpublished amendment path",
        ),
        (with_outcome(relation="direct_to_final"), "Direct outcome"),
        (with_outcome(article_id=None), "needs an article"),
        (with_outcome(article_id="art:absent"), "Missing referenced"),
        (
            replace(
                FIXTURE,
                articles=tuple(
                    changed(row, stage="proposal") if row.article_id == ARTICLE.article_id else row
                    for row in FIXTURE.articles
                ),
            ),
            "different stage or procedure",
        ),
        (
            with_outcome(spans=(FINAL.spans[0].model_copy(update={"field": "new_text"}),)),
            "Outcome evidence",
        ),
        (
            replace(
                FIXTURE,
                documents=tuple(
                    changed(row, procedure_id=FIXTURE.laws[1].procedure_id)
                    if row.document_id == ASK.document_id
                    else row
                    for row in FIXTURE.documents
                ),
            ),
            "Source .* another procedure",
        ),
    ],
)
def test_invalid_public_paths_fail_explicitly(fixture: AtlasFixture, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        graph(fixture)


def test_duplicate_and_reordered_inputs_are_idempotent() -> None:
    duplicate = replace(
        FIXTURE,
        asks=(*FIXTURE.asks, ASK),
        links=(*FIXTURE.links, LINK),
        actors=tuple(reversed(FIXTURE.actors)),
        laws=tuple(reversed(FIXTURE.laws)),
        outcomes=tuple(reversed(FIXTURE.outcomes)),
    )
    assert graph(duplicate).model_dump_json() == graph(FIXTURE).model_dump_json()


def test_golden_fixture_path_relations_and_citations() -> None:
    snapshot = graph(FIXTURE)
    golden = FIXTURE.graphs[0]
    expected = {(edge.relation, edge.source, edge.target) for edge in golden.edges}
    actual = {(edge.relation, edge.source, edge.target) for edge in snapshot.edges}
    assert expected <= actual
    assert len(snapshot.edges) == 9
    for expected_edge in golden.edges:
        actual_edge = next(
            edge
            for edge in snapshot.edges
            if (edge.relation, edge.source, edge.target)
            == (expected_edge.relation, expected_edge.source, expected_edge.target)
        )
        if expected_edge.relation in {"ECHOED_BY", "REALIZED_IN"}:
            assert actual_edge.spans == expected_edge.spans
            assert actual_edge.link_id == expected_edge.link_id
            assert actual_edge.outcome_id == expected_edge.outcome_id


def test_passage_coordinates_joint_attribution_and_unlinked_final() -> None:
    span = LINK.ask_spans[0]
    local_span = span.model_copy(
        update={
            "record_id": ASK.passage_id,
            "start": span.start - ASK.span.start,
            "end": span.end - ASK.span.start,
        }
    )
    fixture = replace(
        with_ask(joint_actor_ids=(FIXTURE.actors[1].actor_id, ASK.actor_id), requested_change=None),
        links=(changed(LINK, ask_spans=(local_span,)),),
        outcomes=(
            changed(
                FINAL, relation="direct_to_final", amendment_id=None, link_id=None, result="partial"
            ),
        ),
    )
    snapshot = graph(fixture)
    assert len([edge for edge in snapshot.edges if edge.relation == "REQUESTED"]) == 2
    assert (
        next(node for node in snapshot.nodes if node.node_id == ASK.ask_id).label == ASK.span.text
    )
    assert [edge.source for edge in snapshot.edges if edge.relation == "REALIZED_IN"] == [
        ASK.ask_id
    ]
    assert not any(edge.relation == "ALIGNED_TO" for edge in snapshot.edges)


def test_no_links_or_outcomes_preserves_unknowns_and_coverage() -> None:
    empty = graph(replace(FIXTURE, links=()))
    assert empty.edges == ()
    assert {node.kind for node in empty.nodes} == {"procedure"}
    snapshot = graph(replace(with_ask(passage_id=None), outcomes=()))
    assert not any(edge.relation == "REALIZED_IN" for edge in snapshot.edges)
    assert len([edge for edge in snapshot.edges if edge.relation == "ECHOED_BY"]) == 2


def test_outcome_cannot_use_unconfirmed_link_even_with_same_endpoints() -> None:
    unconfirmed = changed(LINK, link_id="link:unconfirmed-duplicate", status="unconfirmed")
    fixture = replace(
        FIXTURE,
        links=(*FIXTURE.links, unconfirmed),
        outcomes=(changed(FINAL, link_id=unconfirmed.link_id),),
    )
    with pytest.raises(ValueError, match="unpublished link"):
        graph(fixture)


def test_conflicting_results_fail_but_distinct_support_is_retained() -> None:
    other = changed(FINAL, outcome_id="outcome:extra-support")
    result = graph(replace(FIXTURE, outcomes=(FINAL, other)))
    assert len([edge for edge in result.edges if edge.relation == "REALIZED_IN"]) == 2
    with pytest.raises(ValueError, match="Conflicting outcome results"):
        graph(replace(FIXTURE, outcomes=(FINAL, changed(other, result="partial"))))


def test_multiple_published_links_share_attribution_and_amendment_nodes() -> None:
    other = changed(LINK, link_id="link:extra-support")
    fixture = replace(FIXTURE, links=(LINK, other), outcomes=(FINAL,))
    snapshot = graph(fixture)
    assert len([edge for edge in snapshot.edges if edge.relation == "ECHOED_BY"]) == 2
    assert len([edge for edge in snapshot.edges if edge.relation == "REQUESTED"]) == 1
    assert len([node for node in snapshot.nodes if node.kind == "amendment"]) == 1
    assert snapshot == graph(replace(fixture, links=(other, LINK)))


def test_request_span_can_index_passage_text() -> None:
    local = ASK.span.model_copy(
        update={"record_id": ASK.passage_id, "start": 0, "end": len(ASK.span.text)}
    )
    snapshot = graph(with_ask(span=local))
    requested = next(
        edge
        for edge in snapshot.edges
        if edge.relation == "REQUESTED" and edge.target == ASK.ask_id
    )
    assert requested.spans == (local,)
