"""An audit for one frozen configuration must never transfer to another configuration."""

from dataclasses import replace

import pytest

from influence.services.audit import AuditReport, wilson_interval
from influence.services.calculation import (
    METHOD,
    PublicationEvidence,
    calculate_links,
    model_digest,
)
from influence.services.calibration import FittedCombiner, fit_combiner
from influence.services.signals import SignalCorpus


@pytest.fixture
def model() -> FittedCombiner:
    return fit_combiner(((0.0,), (1.0,)), (False, True), ("lexical_overlap",), training_id="train")


@pytest.fixture
def corpus() -> SignalCorpus:
    return SignalCorpus(("fixed training record", "second independent record"))


@pytest.fixture
def policy(model: FittedCombiner, corpus: SignalCorpus) -> PublicationEvidence:
    low, high = wilson_interval(40, 40)
    return PublicationEvidence(
        cutoff=0.8,
        audited_cutoff=0.8,
        model_digest=model_digest(model, corpus),
        feature_names=model.feature_names,
        calculation_revision=METHOD,
        training_id="train",
        development_id="dev",
        audit_id="audit",
        training_sample_ids=frozenset({"train1", "train2"}),
        development_sample_ids=frozenset({"dev1"}),
        audit_sample_ids=frozenset(f"audit{i}" for i in range(40)),
        minimum_precision=0.9,
        minimum_samples=30,
        report=AuditReport(
            sampled=40,
            resolved=40,
            correct=40,
            unresolved=0,
            unlabelled=0,
            precision=1.0,
            low=low,
            high=high,
            by_tier={"copied": (40, 40)},
        ),
    )


def test_digest_changes_with_every_frozen_model_input(
    model: FittedCombiner, corpus: SignalCorpus
) -> None:
    original = model_digest(model, corpus)
    changed = [
        model_digest(model.model_copy(update={"intercept": model.intercept + 0.1}), corpus),
        model_digest(model, SignalCorpus(("different training corpus",))),
        model_digest(model, corpus, semantic_model=("encoder", "v1")),
        model_digest(model, corpus, semantic_model=("encoder", "v2")),
        model_digest(model, corpus, entailment_model=("judge", "v1")),
        model_digest(model, corpus, entailment_model=("judge", "v2")),
        model_digest(model, corpus, entailment_decision="decision-v1"),
        model_digest(model, corpus, entailment_decision="decision-v2"),
    ]
    assert original not in changed
    assert len(set(changed)) == len(changed)
    assert model_digest(model, corpus) == original


@pytest.mark.parametrize(
    ("semantic", "judge", "decision"),
    [(("encoder", "v1"), None, None), (None, ("judge", "v1"), None), (None, None, "decision-v1")],
)
def test_enabling_a_model_cannot_reuse_a_previous_audit(
    policy: PublicationEvidence,
    model: FittedCombiner,
    corpus: SignalCorpus,
    semantic: tuple[str, str] | None,
    judge: tuple[str, str] | None,
    decision: str | None,
) -> None:
    # Audit validation occurs before candidates, so empty input cannot hide a stale audit.
    assert (
        calculate_links(
            (),
            amendments={},
            asks={},
            source_texts={},
            corpus=corpus,
            combiner=model,
            publication={"copied": policy},
        )
        == ()
    )
    with pytest.raises(ValueError, match="model/features/calculation"):
        calculate_links(
            (),
            amendments={},
            asks={},
            source_texts={},
            corpus=corpus,
            combiner=model,
            publication={"copied": policy},
            semantic_model=semantic,
            entailment_model=judge,
            entailment_decision=decision,
        )


@pytest.mark.parametrize("revision", ["encoder", "judge", "decision"])
def test_changing_enabled_model_revision_invalidates_audit(
    policy: PublicationEvidence, model: FittedCombiner, corpus: SignalCorpus, revision: str
) -> None:
    original = model_digest(
        model,
        corpus,
        semantic_model=("encoder", "v1"),
        entailment_model=("judge", "v1"),
        entailment_decision="v1",
    )
    audited = replace(policy, model_digest=original)
    with pytest.raises(ValueError, match="model/features/calculation"):
        calculate_links(
            (),
            amendments={},
            asks={},
            source_texts={},
            corpus=corpus,
            combiner=model,
            publication={"copied": audited},
            semantic_model=("encoder", "v2" if revision == "encoder" else "v1"),
            entailment_model=("judge", "v2" if revision == "judge" else "v1"),
            entailment_decision="v2" if revision == "decision" else "v1",
        )
