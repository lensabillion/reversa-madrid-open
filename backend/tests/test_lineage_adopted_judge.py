"""Semantic judgments must target an exact accepted amendment/final occurrence."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pydantic import ValidationError
from test_collected import LATER
from test_jev_judge import SUPPORTING, FakeJev
from test_lineage_assembly import NOW
from test_lineage_carrier_evidence import amendment, article
from test_lineage_jev import offline_judge, semantic_world
from test_lineage_views import adopted_world

from influence.schemas.atlas import (
    Amendment,
    ArticleVersion,
    Ask,
    DocumentText,
    Passage,
    SourceSpan,
)
from influence.schemas.lineage import AdoptionEvidence, LineageView, OriginJudgment, OriginSupport
from influence.services import jev, jev_judge, lineage_assembly
from influence.services.collected import Collected, PipelineError
from influence.services.jev_judge import adopted_origin_request, request_bytes
from influence.services.lineage import adopt
from influence.services.lineage_candidates import asks_from_passages
from influence.services.lineage_jev import reworded_origins


def test_an_acceptance_for_the_second_interval_cannot_be_assigned_to_the_first(
    tmp_path: Path,
) -> None:
    first = " ".join(f"novel{i}" for i in range(12))
    second = " ".join(f"novel{i}" for i in range(12, 24))
    rejected = " ".join(f"rejected{i}" for i in range(12))
    world = semantic_world()
    world = replace(
        world,
        amendments=(amendment(1, f"{first} {rejected} {second}"),),
        articles=(
            article("baseline proposal wording", "proposal", "proposal"),
            article(f"{first} separator {second}"),
        ),
    )
    adoption = adopt(world)
    assert len(adoption.phrases) == 2
    fake = FakeJev(
        answer=lambda state: (
            SUPPORTING
            if "novel17" in str(state.get("surviving_amendment_span"))
            else {**SUPPORTING, "same_legal_change": 0.1}
        )
    )
    found, _ = reworded_origins(
        world, adoption.adoptions, offline_judge(tmp_path, fake), submitters={}
    )
    assert len(fake.states) == 2
    (origin,) = found
    assert origin.phrase_id == next(p.phrase_id for p in adoption.phrases if "novel17" in p.text)
    (support,) = origin.supports
    assert support.kind == "semantic"
    assert support.judgment is not None
    assert support.judgment.prompt_revision == "adopted-origin-v1"
    evidence = next(
        e for e in adoption.adoptions[0].evidence if e.evidence_id == support.adoption_evidence_id
    )
    assert support.amendment_span == evidence.amendment_span
    assert support.final_span == evidence.final_span
    assert all(state["amendment_new"] == world.amendments[0].new_text for state in fake.states)


def test_missing_adoption_evidence_never_becomes_semantic_support(tmp_path: Path) -> None:
    world = semantic_world()
    adoption = adopt(world).adoptions[0].model_copy(update={"evidence": ()})
    fake = FakeJev()
    found, note = reworded_origins(world, [adoption], offline_judge(tmp_path, fake), submitters={})
    assert found == ()
    assert fake.states == []
    assert "missing_carrier_evidence" in note


def request_case() -> tuple[Collected, Ask, Amendment, AdoptionEvidence, ArticleVersion]:
    world = semantic_world()
    ask = next(
        item for item in asks_from_passages(world.passages) if item.document_id.endswith(":9")
    )
    amendment = world.amendments[0]
    evidence = adopt(world).adoptions[0].evidence[0]
    final = next(
        item for item in world.articles if item.article_id == evidence.final_span.record_id
    )
    return world, ask, amendment, evidence, final


def test_the_adopted_request_preserves_full_context_and_changes_cache_identity() -> None:
    _, ask, amendment, evidence, final = request_case()
    source = ask.span.text
    prepared = adopted_origin_request(ask, amendment, evidence, source, final, {})
    request = prepared
    assert isinstance(request, jev.JevRequest)
    assert isinstance(request.state, dict)
    assert request.state["prompt_revision"] == "adopted-origin-v1"
    assert request.state["amendment_old"] == amendment.old_text
    assert request.state["amendment_new"] == amendment.new_text
    assert request.state["final_provision_text"] == final.text
    assert request.state["final_provision"] == final.provision
    assert request.state["surviving_amendment_span"] == evidence.amendment_span.model_dump(
        mode="json"
    )
    assert request.state["surviving_final_span"] == evidence.final_span.model_dump(mode="json")
    assert request.state["inserted_word_offsets"] == list(evidence.inserted_word_offsets)
    assert request.state["adoption_evidence_id"] == evidence.evidence_id
    legacy = jev_judge.judge_request(ask, amendment, source, {})
    assert legacy is not None
    assert (
        hashlib.sha256(request_bytes(request)).digest()
        != hashlib.sha256(request_bytes(legacy)).digest()
    )
    question = request.questions["same_legal_change"].instructions
    assert isinstance(question, str)
    assert "rejected or unrelated" in question
    assert "surviving_final_span" in question
    assert "negation" in question


def test_unicode_repeated_asks_use_exact_offsets_and_originals_stay_unknown() -> None:
    _, ask, amendment, evidence, final = request_case()
    prefix = f"😀 café {ask.span.text} Repeated: "
    source = prefix + ask.span.text + "\nFollowing context."
    quoted = ask.model_copy(
        update={
            "span": ask.span.model_copy(
                update={"start": len(prefix), "end": len(prefix) + len(ask.span.text)}
            )
        }
    )
    request = adopted_origin_request(
        quoted, amendment.model_copy(update={"old_text": None}), evidence, source, final, {}
    )
    assert isinstance(request, jev.JevRequest)
    assert isinstance(request.state, dict)
    assert request.state["submission_new"] == ask.span.text
    assert request.state["preceding_context"] == prefix
    assert request.state["following_context"] == "\nFollowing context."
    assert request.state["amendment_old"] is None


def test_only_optional_proposal_is_dropped_and_essential_context_is_never_trimmed() -> None:
    _, ask, amendment, evidence, final = request_case()
    amendment = amendment.model_copy(update={"target_provision": "Article 12"})
    large = {"article 12": "p" * jev.MAX_REQUEST_BYTES}
    request = adopted_origin_request(ask, amendment, evidence, ask.span.text, final, large)
    assert isinstance(request, jev.JevRequest)
    assert isinstance(request.state, dict)
    assert request.state["proposal_text"] is None
    assert (
        request.state["proposal_context_status"] == "omitted_full_provision_exceeds_request_bound"
    )
    exact = adopted_origin_request(
        ask, amendment, evidence, ask.span.text, final, {"article 12": "Proposal context"}
    )
    assert isinstance(exact, jev.JevRequest)
    assert isinstance(exact.state, dict)
    assert exact.state["proposal_text"] == "Proposal context"
    assert exact.state["proposal_context_status"] == "exact_target_provision"
    for changed_amendment, changed_final in [
        (amendment.model_copy(update={"old_text": "x" * jev.MAX_REQUEST_BYTES}), final),
        (
            amendment.model_copy(
                update={"new_text": amendment.new_text + "x" * jev.MAX_REQUEST_BYTES}
            ),
            final,
        ),
        (amendment, final.model_copy(update={"text": final.text + "x" * jev.MAX_REQUEST_BYTES})),
    ]:
        bounded = adopted_origin_request(
            ask, changed_amendment, evidence, ask.span.text, changed_final, {}
        )
        assert bounded == "request_too_large"


def test_missing_essentials_are_skips_and_corrupt_quotes_are_errors() -> None:
    _, ask, amendment, evidence, final = request_case()
    assert (
        adopted_origin_request(ask, amendment, evidence, None, final, {})
        == "missing_submission_source"
    )
    assert (
        adopted_origin_request(ask, amendment, evidence, ask.span.text, None, {})
        == "missing_final_source"
    )
    changes = [
        (
            ask.model_copy(update={"document_id": "doc:hys_attachment:other"}),
            amendment,
            evidence,
            final,
        ),
        (
            ask.model_copy(update={"span": ask.span.model_copy(update={"field": "new_text"})}),
            amendment,
            evidence,
            final,
        ),
        (
            ask,
            amendment,
            evidence.model_copy(
                update={
                    "amendment_span": evidence.amendment_span.model_copy(
                        update={"record_id": "am:2099-0001-COD:IMCO:999"}
                    )
                }
            ),
            final,
        ),
        (
            ask,
            amendment,
            evidence.model_copy(
                update={
                    "amendment_span": evidence.amendment_span.model_copy(update={"field": "text"})
                }
            ),
            final,
        ),
        (ask, amendment, evidence, final.model_copy(update={"stage": "proposal"})),
        (ask, amendment, evidence, final.model_copy(update={"article_id": "art:wrong:1"})),
        (
            ask,
            amendment,
            evidence.model_copy(
                update={"final_span": evidence.final_span.model_copy(update={"field": "new_text"})}
            ),
            final,
        ),
        (ask.model_copy(update={"procedure_id": "2021/0106(COD)"}), amendment, evidence, final),
        (ask, amendment, evidence, final.model_copy(update={"procedure_id": "2021/0106(COD)"})),
        (ask, amendment.model_copy(update={"new_text": "wrong source"}), evidence, final),
        (ask, amendment, evidence, final.model_copy(update={"text": "wrong source"})),
    ]
    for changed_ask, changed_amendment, changed_evidence, changed_final in changes:
        with pytest.raises(PipelineError, match="exact owning sources"):
            adopted_origin_request(
                changed_ask, changed_amendment, changed_evidence, ask.span.text, changed_final, {}
            )
    with pytest.raises(PipelineError, match="exact owning sources"):
        adopted_origin_request(ask, amendment, evidence, "wrong source", final, {})


def test_legacy_cached_answers_cannot_answer_an_adopted_target(tmp_path: Path) -> None:
    _, ask, amendment, evidence, final = request_case()
    legacy = jev_judge.judge_request(ask, amendment, ask.span.text, {})
    new = adopted_origin_request(ask, amendment, evidence, ask.span.text, final, {})
    assert legacy is not None
    assert isinstance(new, jev.JevRequest)
    fake = FakeJev()
    judge = offline_judge(tmp_path, fake)
    old_report = judge.run([legacy])
    new_report = judge.run([new])
    repeated = judge.run([new])
    assert (old_report.asked, new_report.asked, repeated.cached) == (1, 1, 1)
    assert len(fake.states) == 2
    assert "prompt_revision" not in fake.states[0]
    assert fake.states[1]["prompt_revision"] == "adopted-origin-v1"


def test_budget_skips_do_not_emit_semantic_support(tmp_path: Path) -> None:
    world = semantic_world()
    fake = FakeJev()
    found, note = reworded_origins(
        world, adopt(world).adoptions, offline_judge(tmp_path, fake, max_usd=0), submitters={}
    )
    assert found == ()
    assert fake.states == []
    assert "1 budget-skipped" in note
    assert "0 provider/answer failures" in note


def test_semantic_metadata_and_exact_evidence_relationships_are_validated(tmp_path: Path) -> None:
    view = lineage_assembly.build_lineage(
        semantic_world(), generated_at=NOW, judge=offline_judge(tmp_path, FakeJev())
    )
    number = next(index for index, origin in enumerate(view.origins) if origin.kind == "semantic")
    origin = view.origins[number]
    support = origin.supports[0]
    judgment = support.judgment
    assert judgment is not None
    assert judgment.score == origin.similarity == 0.8
    assert len(judgment.request_sha256) == 64

    def changed(**updates: object) -> LineageView:
        origins = list(view.origins)
        origins[number] = origin.model_copy(update=updates)
        return view.model_copy(update={"origins": tuple(origins)})

    for update, reason in [
        ({"score": 0.7}, "weakest directed answer"),
        ({"request_sha256": "not-a-hash"}, "pattern"),
        ({"prompt_revision": "legal-change-v1"}, "adopted-origin-v1"),
        ({"model": "different-model"}, "jev-1.13.0"),
        ({"actual_request": float("nan")}, "finite number"),
    ]:
        with pytest.raises(ValidationError, match=reason):
            OriginJudgment.model_validate(judgment.model_copy(update=update).model_dump())
    with pytest.raises(ValidationError, match="requires its adopted-origin"):
        OriginSupport.model_validate(support.model_copy(update={"judgment": None}).model_dump())
    with pytest.raises(ValidationError, match="carries no model judgment"):
        OriginSupport.model_validate(support.model_copy(update={"kind": "verbatim"}).model_dump())
    with pytest.raises(ValidationError, match="exactly one"):
        LineageView.model_validate(changed(supports=(support, support)).model_dump())
    for field in ("amendment_span", "final_span"):
        span = getattr(support, field)
        altered = span.model_copy(update={"start": span.start + 1, "end": span.end + 1})
        with pytest.raises(ValidationError, match="exact accepted amendment/final pair"):
            LineageView.model_validate(
                changed(supports=(support.model_copy(update={field: altered}),)).model_dump()
            )
    with pytest.raises(ValidationError, match="retained judgment score"):
        LineageView.model_validate(changed(similarity=0.9).model_dump())
    # Earlier semantic suggestions remain unsupported; evidence is never invented.
    for version, revision in (("lineage-1", "lineage-1.1"), ("lineage-2", "lineage-2.0")):
        legacy = changed(supports=()).model_copy(
            update={"schema_version": version, "method_revision": revision}
        )
        loaded = LineageView.model_validate(legacy.model_dump())
        assert loaded.origins[number].supports == ()


def test_a_missing_source_or_wrong_carrier_phrase_has_explicit_diagnostics(tmp_path: Path) -> None:
    world = semantic_world()
    adoptions = adopt(world).adoptions
    fake = FakeJev()
    absent_amendments = replace(world, amendments=())
    found, note = reworded_origins(
        absent_amendments, adoptions, offline_judge(tmp_path / "am", fake), submitters={}
    )
    assert found == ()
    assert "missing_amendment_source=1" in note
    absent_final = replace(
        world, articles=tuple(a for a in world.articles if a.stage != "final_act")
    )
    found, note = reworded_origins(
        absent_final, adoptions, offline_judge(tmp_path / "final", fake), submitters={}
    )
    assert found == ()
    assert "missing_final_source=1" in note
    wrong = adoptions[0].model_copy(
        update={
            "evidence": (
                adoptions[0]
                .evidence[0]
                .model_copy(update={"phrase_id": "phrase:deadbeefdeadbeef"}),
            )
        }
    )
    with pytest.raises(PipelineError, match="different carrier phrase"):
        reworded_origins(world, [wrong], offline_judge(tmp_path / "bad", fake), submitters={})


def test_tabled_only_origins_cannot_carry_adopted_support(tmp_path: Path) -> None:
    view = lineage_assembly.build_lineage(
        semantic_world(), generated_at=NOW, judge=offline_judge(tmp_path, FakeJev())
    )
    tabled = next(
        origin for origin in view.origins if origin.phrase_id == view.tabled_phrases[0].phrase_id
    )
    support = next(origin.supports[0] for origin in view.origins if origin.supports)
    origins = tuple(
        origin.model_copy(update={"supports": (support,)}) if origin == tabled else origin
        for origin in view.origins
    )
    with pytest.raises(ValidationError, match="only to adopted origins"):
        LineageView.model_validate(view.model_copy(update={"origins": origins}).model_dump())


def test_highest_support_candidate_wins_and_ties_use_exact_ask_offsets(tmp_path: Path) -> None:
    world, ask, _, _, _ = request_case()
    later = ask.span.text + " Later."
    whole = ask.span.text + " Separator. " + later
    start = len(ask.span.text + " Separator. ")
    passage = next(p for p in world.passages if p.document_id == ask.document_id)
    later_passage = passage.model_copy(
        update={
            "passage_id": "passage:later",
            "span": SourceSpan(record_id=ask.document_id, start=start, end=len(whole), text=later),
        }
    )
    world = replace(
        world,
        passages=(*world.passages, later_passage),
        document_texts=tuple(
            text.model_copy(update={"text": whole}) if text.document_id == ask.document_id else text
            for text in world.document_texts
        ),
    )
    fake = FakeJev(
        answer=lambda state: {
            **SUPPORTING,
            "same_legal_change": 0.7 if state["submission_new"] == ask.span.text else 0.8,
        }
    )
    best, _ = reworded_origins(
        world, adopt(world).adoptions, offline_judge(tmp_path / "scores", fake), submitters={}
    )
    (origin,) = best
    assert origin.span.start == start
    assert origin.similarity == 0.8
    assert len(fake.states) == 2
    tied, _ = reworded_origins(
        world, adopt(world).adoptions, offline_judge(tmp_path / "ties", FakeJev()), submitters={}
    )
    (origin,) = tied
    assert origin.span == ask.span
    reversed_world = replace(world, passages=tuple(reversed(world.passages)))
    reversed_found, _ = reworded_origins(
        reversed_world,
        adopt(world).adoptions,
        offline_judge(tmp_path / "reversed", FakeJev()),
        submitters={},
    )
    assert tied == reversed_found


def test_lexical_evidence_suppression_does_not_hide_a_sibling_target(tmp_path: Path) -> None:
    first = " ".join(f"novel{i}" for i in range(12))
    second = " ".join(f"novel{i}" for i in range(12, 24))
    world = replace(
        semantic_world(),
        amendments=(amendment(1, f"{first} unrelated {second}"),),
        articles=(
            article("baseline proposal wording", "proposal", "proposal"),
            article(f"{first} separator {second}"),
        ),
    )
    adoption = adopt(world)
    first_evidence = next(
        e for e in adoption.adoptions[0].evidence if "novel0 " in e.amendment_span.text
    )
    fake = FakeJev()
    found, note = reworded_origins(
        world,
        adoption.adoptions,
        offline_judge(tmp_path, fake),
        submitters={},
        known=frozenset({("doc:hys_attachment:9", first_evidence.evidence_id)}),
    )
    assert len(fake.states) == 1
    (origin,) = found
    assert origin.supports[0].adoption_evidence_id != first_evidence.evidence_id
    assert "already_lexical=1" in note


SEMANTIC_FIXTURE = Path(__file__).parent / "fixtures" / "lineage" / "view-semantic-sources-v2.1.json"


def render_semantic_fixture() -> str:
    """A portable real-built view with an offline model fake and deterministic request hashes."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        world = adopted_world(root)
        source = next(d for d in world.documents if d.source_kind == "hys_attachment")
        actor = world.passages[0].actor_id
        source = source.model_copy(
            update={
                "document_id": "doc:hys_attachment:semantic-test",
                "title": "Synthetic semantic fixture",
            }
        )
        text = "Please require logs retention for six months once each system enters the market."
        passage = Passage(
            passage_id="passage:semantic-test",
            procedure_id=world.law.procedure_id,
            document_id=source.document_id,
            actor_id=actor,
            span=SourceSpan(record_id=source.document_id, start=0, end=len(text), text=text),
            submitted_at=source.published_at,
        )
        world = replace(
            world,
            documents=(*world.documents, source),
            document_texts=(
                *world.document_texts,
                DocumentText(document_id=source.document_id, text=text),
            ),
            passages=(*world.passages, passage),
        )
        view = lineage_assembly.build_lineage(
            world, generated_at=LATER, judge=offline_judge(root, FakeJev())
        )
        assert any(origin.kind == "semantic" and origin.supports for origin in view.origins)
        return json.dumps(view.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def test_the_semantic_frontend_fixture_is_built_from_exact_targeted_requests() -> None:
    assert SEMANTIC_FIXTURE.read_text() == render_semantic_fixture()


if __name__ == "__main__":
    SEMANTIC_FIXTURE.write_text(render_semantic_fixture())
    print(f"Wrote {SEMANTIC_FIXTURE}")
