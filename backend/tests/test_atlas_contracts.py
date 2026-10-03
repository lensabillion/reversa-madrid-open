"""The shared Atlas contracts: every rule that keeps unknowns, evidence and IDs honest."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from atlas_fixture import (
    AM1,
    AM1_NEW,
    ARTICLE_TEXTS,
    CASES,
    FIXTURE_DIRECTORY,
    LAW_A,
    LAW_B,
    AtlasFixture,
    build_fixture,
    render,
    write_fixture,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from influence.schemas.atlas import (
    ATLAS_SCHEMA_VERSION,
    Actor,
    Amendment,
    AtlasRecord,
    Forecast,
    GraphEdge,
    GraphSnapshot,
    LawRecord,
    LayerCoverage,
    LinkAssessment,
    Outcome,
    RunManifest,
    SourceSpan,
    document_id,
    id_part,
    mep_actor_id,
    named_actor_id,
    register_actor_id,
    span_matches,
)

PROPERTY = settings(derandomize=True, database=None, deadline=None)
FIXTURE = build_fixture()
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def changed[T: AtlasRecord](record: T, **updates: object) -> T:
    """Revalidate a fixture record with some fields replaced."""
    return type(record).model_validate({**record.model_dump(), **updates})


def link(case: str) -> LinkAssessment:
    return next(item for item in FIXTURE.links if item.link_id == CASES[case])


def outcome(case: str) -> Outcome:
    return next(item for item in FIXTURE.outcomes if item.outcome_id == CASES[case])


# --- The committed files ----------------------------------------------------------------


def test_committed_fixture_files_match_the_builder() -> None:
    for stem, records in FIXTURE.tables().items():
        path = FIXTURE_DIRECTORY / f"{stem}.jsonl"
        assert path.read_text(encoding="utf-8") == render(records), path.name
    assert json.loads((FIXTURE_DIRECTORY / "cases.json").read_text(encoding="utf-8")) == CASES


def test_write_fixture_reproduces_the_committed_files(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    written = sorted(path.name for path in tmp_path.iterdir())
    assert written == sorted(
        path.name for path in FIXTURE_DIRECTORY.iterdir() if path.suffix in {".json", ".jsonl"}
    )
    for name in written:
        assert (tmp_path / name).read_bytes() == (FIXTURE_DIRECTORY / name).read_bytes(), name


def test_every_fixture_line_validates_and_carries_the_schema_version() -> None:
    for stem, records in FIXTURE.tables().items():
        lines = (FIXTURE_DIRECTORY / f"{stem}.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == len(records) > 0, stem
        for line, record in zip(lines, records, strict=True):
            assert type(record).model_validate_json(line) == record
            assert json.loads(line)["schema_version"] == ATLAS_SCHEMA_VERSION


# --- Evidence and joins -----------------------------------------------------------------


def _texts(fixture: AtlasFixture) -> dict[tuple[str, str], str]:
    """(record ID, field) -> the text a span with that address indexes."""
    texts = {(item.document_id, "text"): item.text for item in fixture.document_texts}
    texts.update({(article_id, "text"): text for article_id, text in ARTICLE_TEXTS.items()})
    for amendment in fixture.amendments:
        texts[amendment.amendment_id, "new_text"] = amendment.new_text
        texts[amendment.amendment_id, "old_text"] = amendment.old_text or ""
    return texts


def _spans(fixture: AtlasFixture) -> list[SourceSpan]:
    spans = [item.span for item in (*fixture.passages, *fixture.asks, *fixture.positions)]
    for item in fixture.links:
        spans.extend((*item.amendment_spans, *item.ask_spans))
    for item in fixture.outcomes:
        spans.extend(item.spans)
    for graph in fixture.graphs:
        for edge in graph.edges:
            spans.extend(edge.spans)
    return spans


def test_every_fixture_span_quotes_its_source_exactly() -> None:
    texts = _texts(FIXTURE)
    spans = _spans(FIXTURE)
    assert len(spans) > 20
    for span in spans:
        assert span_matches(span, texts[span.record_id, span.field]), span


def test_fixture_records_join_on_their_identifiers() -> None:
    documents = {item.document_id for item in FIXTURE.documents}
    actors = {item.actor_id for item in FIXTURE.actors}
    asks = {item.ask_id for item in FIXTURE.asks}
    amendments = {item.amendment_id for item in FIXTURE.amendments}
    candidates = {item.candidate_id for item in FIXTURE.candidates}
    links = {item.link_id for item in FIXTURE.links}
    articles = {item.article_id for item in FIXTURE.articles}
    laws = {item.procedure_id for item in FIXTURE.laws}
    assert laws == {LAW_A, LAW_B}
    assert {item.document_id for item in FIXTURE.document_texts} <= documents
    for passage in FIXTURE.passages:
        assert passage.document_id in documents
        assert passage.actor_id in actors
    for amendment in FIXTURE.amendments:
        assert amendment.document_id in documents
        assert set(amendment.author_ids) <= actors
    for ask in FIXTURE.asks:
        assert ask.actor_id in actors
        assert ask.passage_id in {item.passage_id for item in FIXTURE.passages}
    for candidate in FIXTURE.candidates:
        assert candidate.amendment_id in amendments
        assert candidate.ask_id in asks
    for item in FIXTURE.links:
        assert item.candidate_id in candidates
        assert item.amendment_id in amendments
        assert item.ask_id in asks
    for item in FIXTURE.outcomes:
        assert item.ask_id in asks
        assert item.link_id is None or item.link_id in links
        assert item.article_id is None or item.article_id in articles
    # Every observed ask has an outcome, including asks with no published link.
    assert {item.ask_id for item in FIXTURE.outcomes} == asks
    for actor in FIXTURE.actors:
        assert set(actor.candidate_ids) <= actors


def test_the_graph_shows_published_links_only() -> None:
    (graph,) = FIXTURE.graphs
    published = {item.link_id for item in FIXTURE.links if item.status == "published"}
    shown = {edge.link_id for edge in graph.edges if edge.relation == "ECHOED_BY"}
    assert shown == {CASES["supported_copy"]}
    assert shown <= published
    assert graph.run_id in {item.run_id for item in FIXTURE.manifests}


# --- The seven cases --------------------------------------------------------------------


def test_fixture_covers_the_seven_handoff_cases() -> None:
    assert link("supported_copy").status == "published"
    assert link("supported_copy").tier == "copied"
    assert link("opposite_request").status == "contradicted"
    assert link("opposite_request").signals["polarity_conflict"] == 1.0
    short = link("short_shall_may_edit")
    assert short.status == "unconfirmed"
    assert [span.text for span in short.amendment_spans] == ["may"]
    ambiguous = next(item for item in FIXTURE.actors if item.actor_id == CASES["ambiguous_actor"])
    assert ambiguous.resolution == "ambiguous"
    assert ambiguous.register_id is None
    assert len(ambiguous.candidate_ids) == 2
    undated = link("missing_date")
    assert undated.time_eligibility == "unknown_date"
    assert undated.status == "unconfirmed"
    assert undated.support_score == link("supported_copy").support_score
    missing = outcome("missing_final_act")
    assert missing.result == "unknown"
    assert missing.reason
    law_b = next(item for item in FIXTURE.laws if item.procedure_id == LAW_B)
    assert law_b.celex_final is None
    assert {item.layer: item.status for item in law_b.coverage}["final_act"] == "missing"
    assert outcome("partial_outcome").result == "partial"


# --- Identifiers ------------------------------------------------------------------------


def test_identifier_builders() -> None:
    assert document_id("hys_feedback", "2665480") == "doc:hys_feedback:2665480"
    assert document_id("cellar", "celex/32024R1689 (EN)") == "doc:cellar:celex-32024R1689-EN"
    assert register_actor_id("880143435725-46") == "actor:tr:880143435725-46"
    assert mep_actor_id(124831) == "actor:mep:124831"
    assert named_actor_id("hys_feedback", "acme corp") == "actor:name:hys_feedback.acme-corp"
    with pytest.raises(ValueError, match="No usable identifier"):
        id_part(" /() ")


@PROPERTY
@given(st.text(min_size=1))
def test_id_part_is_safe_or_refuses(value: str) -> None:
    try:
        part = id_part(value)
    except ValueError:
        return
    assert part
    assert all(
        character.isascii() and (character.isalnum() or character in "._-") for character in part
    )
    assert id_part(part) == part


@pytest.mark.parametrize("procedure", ["2021/106(COD)", "2021-0106-COD", "2021/0106", ""])
def test_procedure_id_must_be_a_full_reference(procedure: str) -> None:
    with pytest.raises(ValidationError):
        changed(FIXTURE.laws[0], procedure_id=procedure)


def test_extra_fields_and_mutation_are_rejected() -> None:
    with pytest.raises(ValidationError):
        changed(FIXTURE.laws[0], unexpected=1)
    with pytest.raises(ValidationError):
        FIXTURE.laws[0].title = "changed"  # type: ignore[misc]  # pyright: ignore[reportAttributeAccessIssue]


# --- Validators -------------------------------------------------------------------------


def test_span_length_must_match_its_text() -> None:
    with pytest.raises(ValidationError, match="code points"):
        SourceSpan(record_id="doc:cellar:x", start=0, end=4, text="abc")


def test_span_offsets_count_code_points_not_utf16_units() -> None:
    source = "\U0001d54f shall 'may'"
    span = SourceSpan(record_id="doc:cellar:x", start=8, end=13, text="'may'")
    assert span_matches(span, source)
    assert not span_matches(span, source.replace("may", "can"))


@PROPERTY
@given(st.text(min_size=1, max_size=40), st.text(max_size=20), st.text(max_size=20))
def test_span_built_from_any_text_matches_only_that_text(
    quote: str, before: str, after: str
) -> None:
    span = SourceSpan(
        record_id="doc:cellar:x", start=len(before), end=len(before) + len(quote), text=quote
    )
    assert span_matches(span, before + quote + after)


def test_coverage_gap_needs_a_reason_and_complete_does_not() -> None:
    assert LayerCoverage(layer="asks", status="complete", count=0).reason is None
    with pytest.raises(ValidationError, match="must say why"):
        LayerCoverage(layer="asks", status="missing")


def test_law_lists_each_layer_once() -> None:
    law = FIXTURE.laws[0]
    with pytest.raises(ValidationError, match="more than once"):
        LawRecord.model_validate({**law.model_dump(), "coverage": [*law.coverage, law.coverage[0]]})


def test_amendment_keeps_unknown_original_apart_from_an_insertion() -> None:
    amendment = FIXTURE.amendments[0]
    assert changed(amendment, old_text=None).old_text is None
    assert changed(amendment, old_text="").old_text == ""
    assert changed(amendment, new_text="").new_text == ""
    with pytest.raises(ValidationError, match="original or proposed"):
        Amendment.model_validate({**amendment.model_dump(), "old_text": None, "new_text": " "})


def test_actor_identity_must_match_how_it_was_resolved() -> None:
    organisation = FIXTURE.actors[0]
    with pytest.raises(ValidationError, match="register ID"):
        changed(organisation, register_id=None)
    mep = next(item for item in FIXTURE.actors if item.kind == "mep")
    with pytest.raises(ValidationError, match="MEP ID"):
        changed(mep, mep_id=None)
    ambiguous = next(item for item in FIXTURE.actors if item.resolution == "ambiguous")
    with pytest.raises(ValidationError, match="candidates"):
        Actor.model_validate({**ambiguous.model_dump(), "candidate_ids": []})


def test_published_link_must_be_dated_quoted_and_tiered() -> None:
    published = link("supported_copy")
    with pytest.raises(ValidationError, match="dated before"):
        changed(published, time_eligibility="unknown_date")
    with pytest.raises(ValidationError, match="dated before"):
        changed(published, time_eligibility="amendment_first")
    with pytest.raises(ValidationError, match="quotes both"):
        changed(published, ask_spans=())
    with pytest.raises(ValidationError, match="quotes both"):
        changed(published, amendment_spans=())
    with pytest.raises(ValidationError, match="evidence tier"):
        changed(published, tier=None)
    assert changed(published, status="unconfirmed", tier=None, ask_spans=()).ask_spans == ()


def test_support_score_is_bounded() -> None:
    for score in (-0.01, 1.01, float("nan")):
        with pytest.raises(ValidationError):
            changed(link("supported_copy"), support_score=score)


def test_outcome_rules() -> None:
    won = next(item for item in FIXTURE.outcomes if item.result == "full")
    with pytest.raises(ValidationError, match="must say why"):
        changed(outcome("missing_final_act"), reason=None)
    with pytest.raises(ValidationError, match="quotes the text"):
        changed(won, spans=())
    with pytest.raises(ValidationError, match="names that amendment"):
        changed(won, amendment_id=None)
    direct = changed(won, relation="direct_to_final", amendment_id=None, link_id=None)
    assert direct.amendment_id is None
    assert changed(won, result="not_observed", spans=()).spans == ()


def test_forecast_score_matches_its_type() -> None:
    scenario = FIXTURE.forecasts[0]
    assert scenario.score is None
    with pytest.raises(ValidationError, match="describes the scenario"):
        changed(scenario, scenario=None)
    with pytest.raises(ValidationError, match="carries its score"):
        changed(scenario, score_type="probability")
    probability = Forecast.model_validate(
        {**scenario.model_dump(), "score_type": "probability", "score": 0.4, "scenario": None}
    )
    assert probability.score == 0.4
    assert changed(scenario, score_type="rule", scenario=None).scenario is None


def test_inferred_edges_need_spans_and_context_edges_do_not() -> None:
    assert GraphEdge(edge_id="e", relation="TABLED_BY", source="a", target="b").spans == ()
    for relation in ("ECHOED_BY", "ALIGNED_TO", "REALIZED_IN"):
        with pytest.raises(ValidationError, match="must carry the spans"):
            GraphEdge.model_validate(
                {"edge_id": "e", "relation": relation, "source": "a", "target": "b"}
            )


def test_snapshot_rejects_dangling_edges_and_repeated_nodes() -> None:
    (graph,) = FIXTURE.graphs
    dangling = GraphEdge(edge_id="e", relation="ABOUT", source=AM1, target="art:missing")
    with pytest.raises(ValidationError, match="joins a node"):
        GraphSnapshot.model_validate({**graph.model_dump(), "edges": [dangling]})
    backwards = GraphEdge(edge_id="e", relation="ABOUT", source="art:missing", target=AM1)
    with pytest.raises(ValidationError, match="joins a node"):
        GraphSnapshot.model_validate({**graph.model_dump(), "edges": [backwards]})
    with pytest.raises(ValidationError, match="repeats a node"):
        GraphSnapshot.model_validate(
            {**graph.model_dump(), "nodes": [*graph.nodes, graph.nodes[0]]}
        )


def test_run_is_complete_only_with_a_law_an_end_time_and_no_failed_stage() -> None:
    complete, running = FIXTURE.manifests
    assert running.completed_at is None
    with pytest.raises(ValidationError, match="completion time"):
        changed(complete, completed_at=None)
    with pytest.raises(ValidationError, match="completion time"):
        changed(complete, procedure_id=None)
    failed = complete.stages[0].model_copy(update={"status": "failed"})
    with pytest.raises(ValidationError, match="failed stage"):
        RunManifest.model_validate({**complete.model_dump(), "stages": [failed]})
    assert changed(running, status="failed", completed_at=NOW).status == "failed"


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValidationError):
        changed(FIXTURE.documents[0], retrieved_at=datetime(2026, 10, 3, 12, 0))


def test_amendment_text_constant_is_the_fixture_amendment() -> None:
    assert FIXTURE.amendments[0].new_text == AM1_NEW
