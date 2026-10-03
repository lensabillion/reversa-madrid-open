"""Parts 3 to 7 over a collected law, the explorer's view, its API and the atlas command.

The world is `test_collect`'s, plus one genuinely matching pair: an amendment that inserts
a rare phrase, and a consultation submission, dated before it, that asks for that phrase.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_collect import FEEDBACK, World, make_world, scripted_cli
from test_hys import as_json, feedback, feedback_page
from test_parltrack import committee_record, mep_record, write_dump

from influence import cli
from influence.api import create_app
from influence.extraction.records import StageStore
from influence.repositories import hys
from influence.schemas.atlas import Actor, LawRecord, LinkAssessment, SourceSpan, span_matches
from influence.schemas.scoring import MAX_TOKENS, TOKEN_PATTERN
from influence.services import assessment, pipeline
from influence.services.pipeline import PipelineError

AI_ACT = "2021/0106(COD)"
SLUG = "2021-0106-COD"
RARE = "for at least six months after the system is placed on the market"
LATER = datetime(2026, 10, 3, 12, 30, tzinfo=UTC)


def matching_world(tmp_path: Path) -> World:
    world = make_world(tmp_path)
    write_dump(
        world.inputs.committee_amendments,
        [
            committee_record(),
            committee_record(
                id="PE7-7",
                seq=7,
                old=["Providers shall keep the logs."],
                new=[f"Providers shall keep the logs {RARE}."],
            ),
        ],
    )
    asking = feedback(
        4,
        feedback=f"We propose that providers keep the logs {RARE}.",
        organization="Acme Unknown Lobby",
        trNumber=None,
        userType="COMPANY",
        attachments=[],
    )
    page = as_json(feedback_page([*FEEDBACK, asking], last=True))
    world.scripted.script = [
        (fragment, page if fragment == hys.feedback_url(14488, 0) else response)
        for fragment, response in world.scripted.script
    ]
    return world


def collected(world: World) -> pipeline.Collected:
    return pipeline.load_collected(world.collect().bundle)


# --- The view -------------------------------------------------------------------------------


def test_a_matching_pair_becomes_a_published_copied_link_with_its_graph(tmp_path: Path) -> None:
    view = pipeline.build_view(collected(matching_world(tmp_path)), generated_at=LATER)

    published = [link for link in view.bundle.links if link.status == "published"]
    assert len(published) == 1
    (link,) = published
    assert link.tier == "copied"
    assert link.amendment_id == "am:2021-0106-COD:ENVI:PE7-7"
    assert RARE in [span.text for span in link.amendment_spans]
    assert {link.status for link in view.bundle.links} <= pipeline.SHOWN_STATUSES
    relations = {(edge.relation, edge.link_id) for edge in view.snapshot.edges}
    assert ("ECHOED_BY", link.link_id) in relations
    assert {"REQUESTED", "TABLED_BY", "ABOUT"} <= {relation for relation, _ in relations}
    assert (view.procedure_id, view.slug, view.title) == (
        AI_ACT,
        SLUG,
        "Artificial Intelligence Act",
    )
    assert (view.ask_method, view.limitations) == (pipeline.ASK_METHOD, pipeline.LIMITATIONS)
    # The scoring sentence names the revision and published tiers part 4 actually uses.
    scoring = view.limitations[1]
    assert f"({assessment.METHOD_REVISION})" in scoring
    assert all(f"{tier}-tier" in scoring for tier in assessment.DEFAULT_PUBLISHABLE)
    assert view.coverage == view.bundle.laws[0].coverage
    assert view.generated_at == LATER


def test_every_shown_record_is_reachable_and_every_quote_matches_its_source(
    tmp_path: Path,
) -> None:
    bundle = pipeline.build_view(collected(matching_world(tmp_path)), generated_at=LATER).bundle

    documents = {document.document_id for document in bundle.documents}
    texts = {text.document_id: text.text for text in bundle.document_texts}
    actors = {actor.actor_id for actor in bundle.actors}
    asks = {ask.ask_id: ask for ask in bundle.asks}
    amendments = {amendment.amendment_id: amendment for amendment in bundle.amendments}
    assert {ask.document_id for ask in bundle.asks} <= documents
    assert {amendment.document_id for amendment in bundle.amendments} <= documents
    assert {ask.actor_id for ask in bundle.asks} <= actors
    assert {author for a in bundle.amendments for author in a.author_ids} <= actors
    for link in bundle.links:
        ask = asks[link.ask_id]
        assert all(span_matches(span, texts[ask.document_id]) for span in link.ask_spans)
        amendment = amendments[link.amendment_id]
        for span in link.amendment_spans:
            assert span_matches(span, getattr(amendment, span.field) or "")
    assert {outcome.ask_id for outcome in bundle.outcomes} <= set(asks)


def test_only_asks_with_a_link_they_could_have_caused_are_traced(tmp_path: Path) -> None:
    view = pipeline.build_view(collected(matching_world(tmp_path)), generated_at=LATER)

    (link,) = (link for link in view.bundle.links if link.status == "published")
    stages = {(o.ask_id, o.stage): o.result for o in view.bundle.outcomes}
    assert stages[(link.ask_id, "heard")] == "full"
    assert stages[(link.ask_id, "parliament_position")] == "unknown"
    traced = {o.ask_id for o in view.bundle.outcomes}
    caused = {item.ask_id for item in view.bundle.links if item.status in pipeline.TRACED_STATUSES}
    assert traced == caused
    (row,) = (row for row in view.rankings if row.actor_name == "Acme Unknown Lobby")
    assert row.observed_asks == 1


def test_a_law_without_matches_has_an_empty_but_valid_view(tmp_path: Path) -> None:
    view = pipeline.build_view(collected(make_world(tmp_path)), generated_at=LATER)

    assert all(link.status != "published" for link in view.bundle.links)
    assert view.bundle.laws[0].procedure_id == AI_ACT


def test_the_strongest_traced_link_is_the_origin_published_first() -> None:
    def link(status: str, score: float, name: str) -> dict[str, object]:
        return {
            "link_id": f"link:{name}",
            "procedure_id": AI_ACT,
            "amendment_id": f"am:{name}",
            "ask_id": "ask:a",
            "status": status,
            "support_score": score,
            "time_eligibility": "ask_first",
            "method": "m",
            "method_revision": "r",
        }

    links = [
        LinkAssessment.model_validate(link("unconfirmed", 0.9, "u")),
        LinkAssessment.model_validate(link("contradicted", 1.0, "c")),
    ]
    assert pipeline.origin_links(links)["ask:a"].link_id == "link:u"
    published = {**link("published", 0.5, "p"), "tier": "copied"}
    published |= {
        "amendment_spans": [{"record_id": "am:p", "start": 0, "end": 1, "text": "x"}],
        "ask_spans": [{"record_id": "doc:x:1", "start": 0, "end": 1, "text": "x"}],
    }
    links.append(LinkAssessment.model_validate(published))
    assert pipeline.origin_links(links)["ask:a"].link_id == "link:p"


def test_a_graph_that_cannot_be_built_is_an_explicit_error(tmp_path: Path) -> None:
    law = collected(matching_world(tmp_path))
    without_meps = replace(law, actors=tuple(a for a in law.actors if a.kind != "mep"))

    with pytest.raises(PipelineError, match="graph cannot be built"):
        pipeline.build_view(without_meps, generated_at=LATER)


# --- On disk ------------------------------------------------------------------------------


def test_the_view_is_written_with_the_frontend_names_and_read_back_equal(tmp_path: Path) -> None:
    world = matching_world(tmp_path)
    result = world.collect()
    view = pipeline.build_view(pipeline.load_collected(result.bundle), generated_at=LATER)

    path = pipeline.write_view(view, result.bundle)

    raw = json.loads(path.read_bytes())
    assert "documentTexts" in raw["bundle"]
    assert "document_texts" not in raw["bundle"]
    assert raw["schema_version"] == "atlas-view-1"
    assert pipeline.read_view(tmp_path, SLUG) == view
    (summary,) = pipeline.list_views(tmp_path).laws
    assert (summary.slug, summary.title, summary.published_links) == (
        SLUG,
        "Artificial Intelligence Act",
        1,
    )


def test_absent_and_invalid_views(tmp_path: Path) -> None:
    assert pipeline.read_view(tmp_path, SLUG) is None
    assert pipeline.list_views(tmp_path).laws == ()
    (tmp_path / "laws" / SLUG).mkdir(parents=True)
    (tmp_path / "laws" / SLUG / pipeline.VIEW_FILE).write_text("{}")
    with pytest.raises(PipelineError, match="invalid"):
        pipeline.read_view(tmp_path, SLUG)


def test_a_bundle_without_a_complete_collect_run_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="No completed collect run"):
        pipeline.load_collected(tmp_path)

    result = make_world(tmp_path).collect()
    store = StageStore(result.bundle)
    store.publish(result.manifest.model_copy(update={"stages": result.manifest.stages[:2]}))
    with pytest.raises(PipelineError, match=r"lacks stages \['asks', 'law'\]"):
        pipeline.load_collected(result.bundle)

    law = result.law
    twice = store.save("law", "f" * 64, {"laws.jsonl": (law, law)}, status="complete", seconds=0)
    stages = (*result.manifest.stages[:3], twice)
    store.publish(result.manifest.model_copy(update={"stages": stages}))
    with pytest.raises(PipelineError, match="holds 2 laws"):
        pipeline.load_collected(result.bundle)


# --- Collect keeps every tabling MEP --------------------------------------------------------


def test_an_mep_missing_from_the_dump_still_has_an_identity(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    write_dump(world.inputs.meps, [mep_record(197721)])

    result = world.collect()

    actors = StageStore(result.bundle).read_output(result.manifest.stages[1], "actors.jsonl", Actor)
    names = {actor.actor_id: actor.name for actor in actors}
    assert names["actor:mep:125042"] == "MEP 125042 (not in the Parltrack MEP dump)"
    assert result.manifest.stages[1].counts["meps_not_in_dump"] == 1


# --- The API --------------------------------------------------------------------------------


def built(tmp_path: Path) -> TestClient:
    world = matching_world(tmp_path)
    result = world.collect()
    view = pipeline.build_view(pipeline.load_collected(result.bundle), generated_at=LATER)
    pipeline.write_view(view, result.bundle)
    return TestClient(create_app(atlas_data_root=tmp_path))


def test_the_api_lists_built_laws_and_serves_a_view(tmp_path: Path) -> None:
    client = built(tmp_path)

    listing = client.get("/api/v1/atlas")
    view = client.get(f"/api/v1/atlas/{SLUG}")

    assert listing.status_code == 200
    assert listing.json()["laws"][0]["slug"] == SLUG
    assert view.status_code == 200
    body = view.json()
    assert set(body["bundle"]) == {
        "laws",
        "documents",
        "documentTexts",
        "passages",
        "actors",
        "asks",
        "amendments",
        "articles",
        "links",
        "outcomes",
    }
    assert LawRecord.model_validate(body["bundle"]["laws"][0]).procedure_id == AI_ACT


def test_the_api_answers_unknown_malformed_and_broken_views(tmp_path: Path) -> None:
    client = TestClient(create_app(atlas_data_root=tmp_path))

    assert client.get("/api/v1/atlas").json() == {"laws": []}
    missing = client.get("/api/v1/atlas/2099-0001-COD")
    assert missing.status_code == 404
    assert "make atlas" in missing.json()["detail"]
    assert client.get("/api/v1/atlas/not-a-law").status_code == 422
    (tmp_path / "laws" / SLUG).mkdir(parents=True)
    (tmp_path / "laws" / SLUG / pipeline.VIEW_FILE).write_text("{}")
    assert client.get(f"/api/v1/atlas/{SLUG}").status_code == 500
    assert client.get("/api/v1/atlas").status_code == 500


# --- The command ----------------------------------------------------------------------------


def test_the_atlas_command_collects_builds_and_points_at_the_explorer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world = matching_world(tmp_path)
    scripted_cli(monkeypatch, world)

    status = cli.main(["atlas", AI_ACT, "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    assert status == 0
    assert "Atlas: 1 published, " in output
    assert f"explorer: http://localhost:3000/atlas?law={SLUG}" in output
    assert pipeline.read_view(tmp_path, SLUG) is not None


def test_the_atlas_command_keeps_the_bundle_when_the_view_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world = matching_world(tmp_path)
    scripted_cli(monkeypatch, world)

    def broken(_collected: pipeline.Collected, *, generated_at: datetime) -> pipeline.AtlasView:
        raise PipelineError(f"no view at {generated_at:%H}")

    monkeypatch.setattr(cli, "build_view", broken)

    status = cli.main(["atlas", AI_ACT, "--data-root", str(tmp_path)])

    assert status == 1
    assert "no view at" in capsys.readouterr().err
    assert StageStore(tmp_path / "laws" / SLUG).current() is not None


def test_an_amendment_too_long_to_search_is_a_labelled_gap_not_a_crash(tmp_path: Path) -> None:
    """The first real AI Act run stopped on a long recital amendment (over 800 tokens)."""
    bundle = collected(matching_world(tmp_path))
    recital = bundle.amendments[0].model_copy(
        update={
            "amendment_id": "am:2021-0106-COD:ENVI:PE7-LONG",
            "old_text": "word " * 900,
            "new_text": "other " * 900,
        }
    )
    view = pipeline.build_view(
        replace(bundle, amendments=(*bundle.amendments, recital)), generated_at=LATER
    )

    assert [link for link in view.bundle.links if link.status == "published"]
    assert view.limitations[: len(pipeline.LIMITATIONS)] == pipeline.LIMITATIONS
    assert view.limitations[-1].startswith("1 amendment(s) were too long or empty to search")
    assert all(link.amendment_id != recital.amendment_id for link in view.bundle.links)


def test_candidates_can_be_found_without_collecting_the_unsearchable(tmp_path: Path) -> None:
    bundle = collected(matching_world(tmp_path))
    recital = bundle.amendments[0].model_copy(update={"old_text": "word " * 900})
    asks = pipeline.asks_from_passages(bundle.passages)
    assert pipeline.find_candidates([recital], asks) == ()


def test_dot_leader_ask_is_excluded_before_retrieval_and_reported(tmp_path: Path) -> None:
    bundle = collected(matching_world(tmp_path))
    passage = bundle.passages[0]
    dotted = "Contents " + "." * 810 + " providers logs market"
    assert len(dotted.split()) < 120
    assert len(TOKEN_PATTERN.findall(dotted)) > MAX_TOKENS
    document = next(
        text for text in bundle.document_texts if text.document_id == passage.document_id
    )
    start = len(document.text) + 1
    original_document = document.model_copy(update={"text": document.text + "\n" + dotted})
    unsupported = passage.model_copy(
        update={
            "passage_id": "passage:dot-leaders",
            "span": SourceSpan(
                record_id=passage.document_id, start=start, end=start + len(dotted), text=dotted
            ),
        }
    )
    with_unsupported = replace(
        bundle,
        passages=(*bundle.passages, unsupported),
        document_texts=tuple(
            original_document if text.document_id == passage.document_id else text
            for text in bundle.document_texts
        ),
    )
    original = unsupported.model_dump_json()
    asks = pipeline.asks_from_passages(with_unsupported.passages)
    rejected: dict[str, str] = {}
    candidates = pipeline.find_candidates(bundle.amendments, asks, unsearchable_asks=rejected)
    bad_id = asks[-1].ask_id
    assert rejected.keys() == {bad_id}
    assert "800 tokens" in rejected[bad_id]
    assert all(candidate.ask_id != bad_id for candidate in candidates)
    assert pipeline.find_candidates(bundle.amendments, asks) == candidates
    view = pipeline.build_view(with_unsupported, generated_at=LATER)
    assert [link for link in view.bundle.links if link.status == "published"]
    assert view.limitations[-1].startswith("1 ask(s) could not be assessed")
    assert bad_id in view.limitations[-1]
    assert "800 tokens" in view.limitations[-1]
    assert "collected bundle" in view.limitations[-1]
    assert unsupported.model_dump_json() == original
    assert original_document.text[unsupported.span.start : unsupported.span.end] == dotted
    assert len(with_unsupported.passages) == len(bundle.passages) + 1
