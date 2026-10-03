"""Synthetic orchestration checks; invented audit labels are not publication evidence."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest
from atlas_fixture import build_fixture

from influence.schemas.atlas import Amendment, Ask, Candidate, LinkAssessment, LinkTier, SourceSpan
from influence.services.audit import AuditReport, wilson_interval
from influence.services.calculation import (
    METHOD,
    EntailmentEvidence,
    PublicationEvidence,
    SemanticEvidence,
    calculate_links,
    model_digest,
    pair_digest,
)
from influence.services.calibration import FittedCombiner, fit_combiner
from influence.services.signals import SignalCorpus

TEXT = "Providers shall retain secure technical logs for six months after sale"
ENCODER = ("synthetic-encoder", "fixed-test-revision")
JUDGE = ("synthetic-judge", "fixed-test-revision")


@dataclass(frozen=True)
class Case:
    candidate: Candidate
    amendment: Amendment
    ask: Ask
    source: str
    model: FittedCombiner
    corpus: SignalCorpus

    def run(
        self,
        *,
        policy: PublicationEvidence | None = None,
        tier: LinkTier = "copied",
        approved: bool = False,
        semantic: SemanticEvidence | None = None,
        judge: EntailmentEvidence | None = None,
        proposal: str | None = None,
    ) -> LinkAssessment:
        digest = model_digest(
            self.model,
            self.corpus,
            semantic_model=ENCODER if semantic else None,
            entailment_model=JUDGE if judge else None,
            entailment_decision="decision-test" if judge else None,
        )
        return calculate_links(
            (self.candidate,),
            amendments={self.amendment.amendment_id: self.amendment},
            asks={self.ask.ask_id: self.ask},
            source_texts={self.ask.span.record_id: self.source},
            combiner=self.model,
            corpus=self.corpus,
            publication={tier: policy} if policy else {},
            semantics={self.candidate.candidate_id: semantic} if semantic else None,
            entailment={self.candidate.candidate_id: judge} if judge else None,
            semantic_model=ENCODER if semantic else None,
            entailment_model=JUDGE if judge else None,
            entailment_decision="decision-test" if judge else None,
            approved_model_digests=frozenset({digest}) if approved else frozenset(),
            proposal_texts={self.candidate.procedure_id: proposal}
            if proposal is not None
            else None,
        )[0]

    def policy(
        self,
        tier: LinkTier = "copied",
        *,
        semantic: bool = False,
        judge: bool = False,
    ) -> PublicationEvidence:
        low, high = wilson_interval(30, 30)
        return PublicationEvidence(
            cutoff=0.0,
            audited_cutoff=0.0,
            model_digest=model_digest(
                self.model,
                self.corpus,
                semantic_model=ENCODER if semantic else None,
                entailment_model=JUDGE if judge else None,
                entailment_decision="decision-test" if judge else None,
            ),
            feature_names=self.model.feature_names,
            calculation_revision=METHOD,
            training_id="train",
            development_id="development",
            audit_id="audit",
            training_sample_ids=frozenset({"t0", "t1"}),
            development_sample_ids=frozenset({"d0"}),
            audit_sample_ids=frozenset(f"a{index}" for index in range(30)),
            minimum_precision=0.8,
            minimum_samples=30,
            report=AuditReport(
                sampled=30,
                resolved=30,
                correct=30,
                unresolved=0,
                unlabelled=0,
                precision=1.0,
                low=low,
                high=high,
                by_tier={tier: (30, 30)},
            ),
        )

    def semantic(self) -> SemanticEvidence:
        return SemanticEvidence(0.9, *ENCODER, pair_digest(self.amendment, self.ask))

    def judge(self, *, supported: bool = True) -> EntailmentEvidence:
        return EntailmentEvidence(
            supported,
            *JUDGE,
            pair_digest(self.amendment, self.ask),
            0.8,
            0.1,
            0.1,
            "decision-test",
            (
                SourceSpan(
                    record_id=self.amendment.amendment_id,
                    field="new_text",
                    start=0,
                    end=len(self.amendment.new_text),
                    text=self.amendment.new_text,
                ),
            ),
            (self.ask.span,),
        )


@pytest.fixture
def case() -> Case:
    fixture = build_fixture()
    amendment = fixture.amendments[0].model_copy(update={"old_text": "", "new_text": TEXT})
    ask = fixture.asks[0].model_copy(
        update={
            "span": SourceSpan(
                record_id=fixture.asks[0].document_id,
                field="text",
                start=0,
                end=len(TEXT),
                text=TEXT,
            ),
            "direction": "unknown",
        }
    )
    model = fit_combiner(((0.0,), (1.0,)), (False, True), ("lexical_overlap",), training_id="train")
    return Case(
        fixture.candidates[0],
        amendment,
        ask,
        TEXT,
        model,
        SignalCorpus(("unrelated training document", "other training material")),
    )


def test_audit_and_explicit_model_acceptance_are_both_required(case: Case) -> None:
    assert case.run().status == "unconfirmed"
    assert case.run(policy=case.policy()).status == "unconfirmed"
    result = case.run(policy=case.policy(), approved=True)
    assert result.status == "published"
    assert result.tier == "copied"
    assert result.signals["submission_original_known"] == 0
    assert result.signals["amendment_original_known"] == 1
    assert result.signals["development_only"] == 0
    assert result.support_score == result.signals["model_support"]
    assert result.amendment_spans[0].text == TEXT
    assert result.ask_spans[0].text == TEXT
    assert any("ordinary prose" in text for text in result.limitations)
    cutoff = replace(
        case.policy(), cutoff=result.support_score, audited_cutoff=result.support_score
    )
    assert case.run(policy=cutoff, approved=True).status == "published"
    assert (
        case.run(policy=replace(cutoff, cutoff=1, audited_cutoff=1), approved=True).status
        == "unconfirmed"
    )


def test_all_fixture_alternatives_retained_in_stable_order() -> None:
    fixture = build_fixture()
    model = fit_combiner(((0.0,), (1.0,)), (False, True), ("lexical_overlap",), training_id="train")
    result = calculate_links(
        tuple(reversed(fixture.candidates)),
        amendments={r.amendment_id: r for r in fixture.amendments},
        asks={r.ask_id: r for r in fixture.asks},
        source_texts={r.document_id: r.text for r in fixture.document_texts},
        corpus=SignalCorpus(("training text only",)),
        combiner=model,
        publication={},
    )
    assert [r.candidate_id for r in result] == sorted(r.candidate_id for r in fixture.candidates)
    assert all(link.status != "published" for link in result)
    assert len({link.link_id for link in result}) == len(result)
    assert {link.time_eligibility for link in result} == {"ask_first", "unknown_date"}


@pytest.mark.parametrize(
    "kind", ["training", "blank", "duplicate", "empty", "blank_sample", "overlap", "count"]
)
def test_audit_requires_disjoint_nonempty_provenance(case: Case, kind: str) -> None:
    policy = case.policy()
    if kind == "training":
        policy = replace(policy, training_id="other")
    elif kind == "blank":
        policy = replace(policy, audit_id=" ")
    elif kind == "duplicate":
        policy = replace(policy, audit_id="development")
    elif kind == "empty":
        policy = replace(policy, development_sample_ids=frozenset())
    elif kind == "blank_sample":
        policy = replace(policy, development_sample_ids=frozenset({" "}))
    elif kind == "overlap":
        policy = replace(policy, development_sample_ids=frozenset({"t0"}))
    else:
        policy = replace(policy, training_sample_ids=frozenset({"t0"}))
    with pytest.raises(ValueError, match="provenance"):
        case.run(policy=policy)


@pytest.mark.parametrize("kind", ["digest", "features", "revision", "corpus"])
def test_audit_matches_frozen_model_and_training_corpus(case: Case, kind: str) -> None:
    policy = case.policy()
    if kind == "digest":
        policy = replace(policy, model_digest="different")
    elif kind == "features":
        policy = replace(policy, feature_names=("alignment",))
    elif kind == "revision":
        policy = replace(policy, calculation_revision="old")
    else:
        case = replace(case, corpus=SignalCorpus(("different corpus",)))
    with pytest.raises(ValueError, match="model/features"):
        case.run(policy=policy)


@pytest.mark.parametrize(
    "kind",
    ["nan", "range", "different", "precision_nan", "precision_range", "count_type", "count_zero"],
)
def test_audit_cutoff_and_targets_are_explicit(case: Case, kind: str) -> None:
    policy = case.policy()
    if kind == "nan":
        policy = replace(policy, cutoff=float("nan"))
    elif kind == "range":
        policy = replace(policy, cutoff=2)
    elif kind == "different":
        policy = replace(policy, audited_cutoff=0.9)
    elif kind == "precision_nan":
        policy = replace(policy, minimum_precision=float("nan"))
    elif kind == "precision_range":
        policy = replace(policy, minimum_precision=0)
    elif kind == "count_type":
        policy = replace(policy, minimum_samples=True)
    else:
        policy = replace(policy, minimum_samples=0)
    with pytest.raises(ValueError, match="minima"):
        case.run(policy=policy)


@pytest.mark.parametrize(
    "kind",
    [
        "negative",
        "nonint",
        "sampled",
        "unresolved",
        "unlabelled",
        "inventory",
        "correct",
        "minimum",
        "tier",
    ],
)
def test_audit_must_be_complete_sufficient_and_tier_specific(case: Case, kind: str) -> None:
    policy = case.policy()
    report = policy.report
    if kind == "negative":
        report = replace(report, correct=-1)
    elif kind == "nonint":
        report = replace(report, correct=True)
    elif kind == "sampled":
        report = replace(report, sampled=31)
    elif kind == "unresolved":
        report = replace(report, unresolved=1)
    elif kind == "unlabelled":
        report = replace(report, unlabelled=1)
    elif kind == "inventory":
        policy = replace(policy, audit_sample_ids=frozenset({"a0"}))
    elif kind == "correct":
        report = replace(report, correct=31)
    elif kind == "minimum":
        policy = replace(policy, minimum_samples=31)
    else:
        report = replace(report, by_tier={"reworded": (30, 30)})
    with pytest.raises(ValueError, match="complete"):
        case.run(policy=replace(policy, report=report))


@pytest.mark.parametrize("kind", ["missing", "precision", "low", "high", "insufficient"])
def test_audit_wilson_is_recomputed_not_trusted(case: Case, kind: str) -> None:
    policy = case.policy()
    report = policy.report
    if kind == "missing":
        report = replace(report, precision=None)
    elif kind == "precision":
        report = replace(report, precision=0.5)
    elif kind == "low":
        report = replace(report, low=1)
    elif kind == "high":
        report = replace(report, high=0.5)
    else:
        policy = replace(policy, minimum_precision=0.999)
    with pytest.raises(ValueError, match="Wilson"):
        case.run(policy=replace(policy, report=report))


def test_semantic_and_judge_features_are_explicit_inputs(case: Case) -> None:
    model = fit_combiner(
        ((0.0, 0.0, 1.0, 0.0), (1.0, 1.0, 0.0, 0.0)),
        (False, True),
        ("semantic_cosine", "entailment_score", "contradiction_score", "neutral_score"),
        training_id="train",
    )
    case = replace(case, model=model)
    with pytest.raises(KeyError, match="semantic_cosine"):
        case.run()
    result = case.run(semantic=case.semantic(), judge=case.judge())
    assert result.signals["semantic_cosine"] == 0.9
    assert result.signals["entailment_score"] == 0.8
    assert result.signals["contradiction_score"] == result.signals["neutral_score"] == 0.1
    assert result.status == "unconfirmed"
    assert (
        case.run(
            semantic=case.semantic(), judge=replace(case.judge(supported=False), contradicted=True)
        ).status
        == "contradicted"
    )


@pytest.mark.parametrize(
    "kind", ["model_blank", "revision_blank", "inputs", "model_changed", "range", "nan"]
)
def test_semantic_provenance_and_finite_range(case: Case, kind: str) -> None:
    evidence = case.semantic()
    if kind == "model_blank":
        evidence = replace(evidence, model_id="")
    elif kind == "revision_blank":
        evidence = replace(evidence, revision=" ")
    elif kind == "inputs":
        evidence = replace(evidence, pair_digest="stale")
    elif kind == "model_changed":
        evidence = replace(evidence, model_id="new encoder")
    elif kind == "range":
        evidence = replace(evidence, cosine=1.1)
    else:
        evidence = replace(evidence, cosine=float("nan"))
    with pytest.raises(ValueError, match="Semantic"):
        case.run(semantic=evidence)


@pytest.mark.parametrize(
    "kind",
    [
        "model",
        "decision",
        "blank_decision",
        "range",
        "nan",
        "sum",
        "am_empty",
        "ask_empty",
        "am_id",
        "am_field",
        "am_text",
        "ask_id",
        "ask_field",
        "ask_before",
        "ask_after",
        "ask_text",
    ],
)
def test_judge_configuration_and_quotes_are_checked(case: Case, kind: str) -> None:
    judge = case.judge()
    am, ask = judge.amendment_spans[0], judge.ask_spans[0]
    if kind == "model":
        judge = replace(judge, model_id="changed judge")
    elif kind == "decision":
        judge = replace(judge, decision_revision="changed decision")
    elif kind == "blank_decision":
        judge = replace(judge, decision_revision="")
    elif kind == "range":
        judge = replace(judge, entailment_score=-0.1)
    elif kind == "nan":
        judge = replace(judge, entailment_score=float("nan"))
    elif kind == "sum":
        judge = replace(judge, neutral_score=0.9)
    elif kind == "am_empty":
        judge = replace(judge, amendment_spans=())
    elif kind == "ask_empty":
        judge = replace(judge, ask_spans=())
    elif kind == "am_id":
        judge = replace(judge, amendment_spans=(am.model_copy(update={"record_id": "other"}),))
    elif kind == "am_field":
        judge = replace(judge, amendment_spans=(am.model_copy(update={"field": "text"}),))
    elif kind == "am_text":
        judge = replace(judge, amendment_spans=(am.model_copy(update={"text": "wrong"}),))
    elif kind == "ask_id":
        judge = replace(judge, ask_spans=(ask.model_copy(update={"record_id": "other"}),))
    elif kind == "ask_field":
        judge = replace(judge, ask_spans=(ask.model_copy(update={"field": "old_text"}),))
    elif kind == "ask_before":
        judge = replace(judge, ask_spans=(ask.model_copy(update={"start": -1}),))
    elif kind == "ask_after":
        judge = replace(judge, ask_spans=(ask.model_copy(update={"end": len(TEXT) + 1}),))
    else:
        judge = replace(judge, ask_spans=(ask.model_copy(update={"text": "wrong"}),))
    with pytest.raises(ValueError, match=r"Entailment|Judge"):
        case.run(judge=judge)


def test_short_change_needs_explicit_entailment_and_its_own_audit(case: Case) -> None:
    text = "replace 'shall' with 'may'"
    case = replace(
        case,
        amendment=case.amendment.model_copy(
            update={
                "old_text": "Operators shall retain logs",
                "new_text": "Operators may retain logs",
            }
        ),
        ask=case.ask.model_copy(
            update={"span": case.ask.span.model_copy(update={"text": text, "end": len(text)})}
        ),
        source=text,
    )
    base = case.run(approved=True, policy=case.policy())
    assert base.status == "insufficient_evidence"
    assert base.tier != "copied"
    assert base.signals["short_edit"] == base.signals["submission_original_known"] == 1
    result = case.run(
        approved=True,
        judge=case.judge(),
        tier="reworded",
        policy=case.policy("reworded", judge=True),
    )
    assert result.status == "published"
    assert result.tier == "reworded"


@pytest.mark.parametrize("kind", ["late", "date_unknown", "original_unknown"])
def test_known_dates_and_original_are_required_for_publication(case: Case, kind: str) -> None:
    if kind == "late":
        case = replace(
            case, ask=case.ask.model_copy(update={"submitted_at": datetime(2100, 1, 1, tzinfo=UTC)})
        )
    elif kind == "date_unknown":
        case = replace(case, ask=case.ask.model_copy(update={"submitted_at": None}))
    else:
        case = replace(case, amendment=case.amendment.model_copy(update={"old_text": None}))
    expected = "insufficient_evidence" if kind == "original_unknown" else "unconfirmed"
    assert case.run(approved=True, policy=case.policy()).status == expected


def test_all_masked_proposal_cannot_publish_even_with_positive_judge(case: Case) -> None:
    assert pair_digest(case.amendment, case.ask) != pair_digest(case.amendment, case.ask, TEXT)
    judge = replace(case.judge(), pair_digest=pair_digest(case.amendment, case.ask, TEXT))
    result = case.run(
        approved=True,
        judge=judge,
        proposal=TEXT,
        tier="reworded",
        policy=case.policy("reworded", judge=True),
    )
    assert result.status == "unconfirmed"
    assert result.signals["submission_fully_masked"] == 1
    assert result.signals["quoted_law_masked_chars"] == len(TEXT)
    assert result.signals["lexical_overlap"] == 0
    assert result.ask_spans == judge.ask_spans
    with pytest.raises(ValueError, match="different inputs"):
        case.run(judge=case.judge(), proposal=TEXT)


def test_common_training_phrases_do_not_qualify_as_copied(case: Case) -> None:
    case = replace(case, corpus=SignalCorpus((TEXT, TEXT)))
    assert case.run(approved=True, policy=case.policy()).tier != "copied"


@pytest.mark.parametrize(
    "kind",
    [
        "amendment_id",
        "ask_id",
        "ask_law",
        "amendment_law",
        "source_id",
        "source_field",
        "source_text",
        "blank_ask",
    ],
)
def test_invalid_joins_and_sources_are_explicit_errors(case: Case, kind: str) -> None:
    if kind == "amendment_id":
        case = replace(
            case, candidate=case.candidate.model_copy(update={"amendment_id": "missing"})
        )
    elif kind == "ask_id":
        case = replace(case, candidate=case.candidate.model_copy(update={"ask_id": "missing"}))
    elif kind == "ask_law":
        case = replace(case, ask=case.ask.model_copy(update={"procedure_id": "other"}))
    elif kind == "amendment_law":
        case = replace(case, amendment=case.amendment.model_copy(update={"procedure_id": "other"}))
    elif kind == "source_id":
        case = replace(
            case,
            ask=case.ask.model_copy(
                update={"span": case.ask.span.model_copy(update={"record_id": "foreign"})}
            ),
        )
    elif kind == "source_field":
        case = replace(
            case,
            ask=case.ask.model_copy(
                update={"span": case.ask.span.model_copy(update={"field": "new_text"})}
            ),
        )
    elif kind == "source_text":
        case = replace(case, source="wrong text")
    else:
        case = replace(
            case,
            source=" ",
            ask=case.ask.model_copy(
                update={"span": case.ask.span.model_copy(update={"text": " ", "end": 1})}
            ),
        )
    with pytest.raises((KeyError, ValueError)):
        case.run()


def test_duplicate_candidates_and_stray_evidence_fail_even_without_publication(case: Case) -> None:
    def run(
        candidates: tuple[Candidate, ...], evidence: Mapping[str, SemanticEvidence]
    ) -> tuple[LinkAssessment, ...]:
        return calculate_links(
            candidates,
            amendments={},
            asks={},
            source_texts={},
            corpus=case.corpus,
            combiner=case.model,
            publication={},
            semantics=evidence,
        )

    with pytest.raises(ValueError, match="unique"):
        run((case.candidate, case.candidate), {})
    with pytest.raises(ValueError, match="absent"):
        run((), {"absent": case.semantic()})
    assert run((), {}) == ()


def test_neutral_judge_is_unconfirmed_not_contradicted(case: Case) -> None:
    judge = replace(
        case.judge(supported=False),
        entailment_score=0.01,
        contradiction_score=0.01,
        neutral_score=0.98,
    )
    result = case.run(judge=judge, approved=True, policy=case.policy(judge=True))
    assert result.status == "unconfirmed"
    assert result.support_score > 0
    assert result.signals["neutral_score"] == 0.98
    with pytest.raises(ValueError, match="Judge scores"):
        case.run(judge=replace(judge, supported=True, contradicted=True))


def test_no_overlap_is_insufficient_not_a_negative_finding(case: Case) -> None:
    text = "Completely unrelated ocean biodiversity conservation"
    case = replace(
        case,
        source=text,
        ask=case.ask.model_copy(
            update={
                "span": case.ask.span.model_copy(update={"text": text, "end": len(text)}),
            }
        ),
    )
    result = case.run()
    assert result.status == "insufficient_evidence"
    assert result.tier is None
    assert result.signals["lexical_overlap"] == 0


def test_masked_punctuation_does_not_count_as_substantive_remaining_prose(case: Case) -> None:
    text = TEXT + "."
    case = replace(
        case,
        source=text,
        ask=case.ask.model_copy(
            update={
                "span": case.ask.span.model_copy(update={"text": text, "end": len(text)}),
            }
        ),
    )
    result = case.run(proposal=TEXT)
    assert result.signals["submission_fully_masked"] == 1
    assert result.signals["lexical_overlap"] == 0
    assert result.status == "insufficient_evidence"


def test_partial_proposal_quote_keeps_unmasked_features_and_original_evidence(case: Case) -> None:
    proposal = (
        "National authorities coordinate environmental inspections "
        "across all jurisdictions within Europe"
    )
    text = proposal + ". " + TEXT
    case = replace(
        case,
        source=text,
        ask=case.ask.model_copy(
            update={
                "span": case.ask.span.model_copy(update={"text": text, "end": len(text)}),
            }
        ),
    )
    result = case.run(proposal=proposal, approved=True, policy=case.policy())
    assert result.status == "published"
    assert result.signals["submission_fully_masked"] == 0
    assert result.signals["quoted_law_masked_chars"] == len(proposal)
    assert result.ask_spans[0].text == TEXT


def test_cross_context_conflicts_veto_even_high_fitted_support(case: Case) -> None:
    text = TEXT.replace("shall", "may")
    case = replace(
        case,
        source=text,
        ask=case.ask.model_copy(
            update={
                "span": case.ask.span.model_copy(update={"text": text, "end": len(text)}),
            }
        ),
    )
    result = case.run(approved=True, policy=case.policy())
    assert result.status == "contradicted"
    assert result.support_score == 0
    assert result.signals["model_support"] > 0.5
    assert result.signals["modal_conflict"] == 1
    assert any("not a finding of legal contradiction" in text for text in result.limitations)


def test_same_direction_stays_unconfirmed_even_with_audit_and_approved_model(case: Case) -> None:
    text = "Providers shall retain"
    case = replace(
        case,
        source=text,
        ask=case.ask.model_copy(
            update={
                "direction": "stricter",
                "span": case.ask.span.model_copy(update={"text": text, "end": len(text)}),
            }
        ),
    )
    result = case.run(approved=True, tier="same_direction", policy=case.policy("same_direction"))
    assert result.tier == "same_direction"
    assert result.status == "unconfirmed"
