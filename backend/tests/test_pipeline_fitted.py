"""One collected fixture feeds combined scoring, outcomes, graph and the same API view."""

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_pipeline import LATER, SLUG, collected, matching_world

from influence.api import create_app
from influence.services.calculation import JevEvidence, SemanticEvidence, pair_digest
from influence.services.calibration import fit_combiner
from influence.services.pipeline import (
    Collected,
    FittedVerification,
    PipelineError,
    asks_from_passages,
    build_view,
    find_candidates,
    write_view,
)
from influence.services.signals import SignalCorpus

FEATURES = (
    "lexical_overlap",
    "rarity_overlap",
    "rare_phrase_overlap",
    "alignment",
    "operation_agreement",
    "negation_conflict",
    "modal_conflict",
    "quantity_conflict",
    "context_comparable",
    "short_edit",
    "background_z",
    "forward_reciprocal_rank",
    "reverse_reciprocal_rank",
    "mutual_reciprocal_rank",
    "semantic_cosine",
    "jev_actual_request",
    "jev_same_legal_change",
    "jev_incompatible_legal_change",
    "jev_shared_background",
)


def configured(tmp_path: Path) -> tuple[Collected, FittedVerification]:
    source = collected(matching_world(tmp_path))
    asks = asks_from_passages(source.passages)
    candidates = find_candidates(source.amendments, asks)
    by_ask = {ask.ask_id: ask for ask in asks}
    by_document = {text.document_id: text.text for text in source.document_texts}
    by_amendment = {amendment.amendment_id: amendment for amendment in source.amendments}
    model = fit_combiner(
        [[0.0] * len(FEATURES), [1.0] * len(FEATURES)],
        [False, True],
        FEATURES,
        training_id="synthetic-integration-only",
    )
    semantics: dict[str, SemanticEvidence] = {}
    jev: dict[str, JevEvidence] = {}
    for candidate in candidates:
        digest = pair_digest(by_amendment[candidate.amendment_id], by_ask[candidate.ask_id])
        semantics[candidate.candidate_id] = SemanticEvidence(0.8, "test-encoder", "1", digest)
        jev[candidate.candidate_id] = JevEvidence(
            0.9,
            0.8,
            0.1,
            0.2,
            "test-jev",
            "1",
            digest,
            "test-prompt-1",
            hashlib.sha256(by_document[by_ask[candidate.ask_id].document_id].encode()).hexdigest(),
        )
    return source, FittedVerification(
        corpus=SignalCorpus([text.text for text in source.document_texts]),
        combiner=model,
        publication={},
        semantics=semantics,
        semantic_model=("test-encoder", "1"),
        jev=jev,
        jev_model=("test-jev", "1"),
        jev_prompt_revision="test-prompt-1",
    )


def test_all_signals_reach_one_view_and_api_without_unaudited_publication(tmp_path: Path) -> None:
    source, verification = configured(tmp_path)
    view = build_view(source, generated_at=LATER, verification=verification)
    assert view.bundle.links
    for link in view.bundle.links:
        assert set(FEATURES) <= link.signals.keys()
        assert link.status != "published"
        assert link.method == "atlas-fitted-signals-v2"
    assert not view.snapshot.edges
    assert "fitted signal model" in view.limitations[1]
    assert "jev_same_legal_change" in view.limitations[1]
    assert all(
        outcome.ask_id in {ask.ask_id for ask in view.bundle.asks}
        for outcome in view.bundle.outcomes
    )
    write_view(view, tmp_path / "laws" / SLUG)
    client = TestClient(create_app(atlas_data_root=tmp_path))
    response = client.get(f"/api/v1/atlas/{SLUG}")
    assert response.status_code == 200
    assert response.json() == view.model_dump(mode="json", by_alias=True)


def test_missing_model_signal_cannot_fall_back_to_lexical(tmp_path: Path) -> None:
    source, verification = configured(tmp_path)
    with pytest.raises(KeyError, match="jev_actual_request"):
        build_view(source, generated_at=LATER, verification=replace(verification, jev={}))


def test_fitted_path_rejects_blanket_prose_override(tmp_path: Path) -> None:
    source, verification = configured(tmp_path)
    with pytest.raises(PipelineError, match="blanket prose override"):
        build_view(source, generated_at=LATER, verification=verification, publish_prose=True)


@pytest.mark.parametrize("signal", ["semantic", "jev"])
def test_changed_model_evidence_changes_joint_support(tmp_path: Path, signal: str) -> None:
    source, verification = configured(tmp_path)
    before = build_view(source, generated_at=LATER, verification=verification)
    assert verification.semantics is not None
    assert verification.jev is not None
    if signal == "semantic":
        changed = replace(
            verification,
            semantics={
                key: replace(value, cosine=0.1) for key, value in verification.semantics.items()
            },
        )
        feature = "semantic_cosine"
    else:
        changed = replace(
            verification,
            jev={
                key: replace(value, same_legal_change=0.1)
                for key, value in verification.jev.items()
            },
        )
        feature = "jev_same_legal_change"
    after = build_view(source, generated_at=LATER, verification=changed)
    before_links = {link.candidate_id: link for link in before.bundle.links}
    assert before_links
    assert set(before_links) == {link.candidate_id for link in after.bundle.links}
    for link in after.bundle.links:
        original = before_links[link.candidate_id]
        assert link.signals[feature] == 0.1
        assert link.signals["model_support"] < original.signals["model_support"]
        assert all(
            link.signals[name] == original.signals[name] for name in FEATURES if name != feature
        )
        assert link.status != "published"
        assert link.method_revision == original.method_revision
