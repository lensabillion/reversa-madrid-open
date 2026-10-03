"""Jev values are optional fitted features, never an implicit publication verdict."""

import hashlib
import json
from dataclasses import replace

import pytest
import test_calculation
from test_calculation import ENCODER, Case

from influence.schemas.atlas import LinkAssessment
from influence.services.assessment import METHOD_REVISION as ASSESSMENT_REVISION
from influence.services.calculation import (
    METHOD,
    JevEvidence,
    SemanticEvidence,
    calculate_links,
    model_digest,
    pair_digest,
)
from influence.services.calibration import fit_combiner

MODEL = ("jev-1.13.0", "jev-1.13.0")
PROMPT = "legal-change-v1:synthetic-prompt-hash"
NAMES = (
    "jev_actual_request",
    "jev_same_legal_change",
    "jev_incompatible_legal_change",
    "jev_shared_background",
)


case = test_calculation.case


def evidence(case: Case) -> JevEvidence:
    return JevEvidence(
        actual_request=0.9,
        same_legal_change=0.8,
        incompatible_legal_change=0.7,
        shared_background=0.6,
        model_id=MODEL[0],
        revision=MODEL[1],
        pair_digest=pair_digest(case.amendment, case.ask),
        prompt_revision=PROMPT,
        source_sha256=hashlib.sha256(case.source.encode()).hexdigest(),
    )


def run(case: Case, rows: dict[str, JevEvidence] | None) -> LinkAssessment:
    return calculate_links(
        (case.candidate,),
        amendments={case.amendment.amendment_id: case.amendment},
        asks={case.ask.ask_id: case.ask},
        source_texts={case.ask.span.record_id: case.source},
        corpus=case.corpus,
        combiner=case.model,
        publication={},
        jev=rows,
        jev_model=MODEL,
        jev_prompt_revision=PROMPT,
    )[0]


def test_independent_values_feed_fitted_support_without_publishing(case: Case) -> None:
    model = fit_combiner(((0.0,) * 4, (1.0,) * 4), (False, True), NAMES, training_id="train")
    case = replace(case, model=model)
    result = run(case, {case.candidate.candidate_id: evidence(case)})
    values = (0.9, 0.8, 0.7, 0.6)
    assert tuple(result.signals[name] for name in NAMES) == values
    assert result.signals["model_support"] == pytest.approx(model.score(values))
    assert result.status == "unconfirmed"
    assert result.signals["development_only"] == 1
    assert "entailment_score" not in result.signals
    assert any("Jev" in limit and PROMPT in limit for limit in result.limitations)
    with pytest.raises(KeyError, match="jev_actual_request"):
        run(case, None)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_id", "wrong"),
        ("model_id", ""),
        ("revision", "wrong"),
        ("revision", ""),
        ("pair_digest", "wrong"),
        ("prompt_revision", "wrong"),
        ("source_sha256", "wrong"),
        ("source_sha256", ""),
        ("actual_request", float("nan")),
        ("same_legal_change", float("inf")),
        ("incompatible_legal_change", -0.01),
        ("shared_background", 1.01),
    ],
)
def test_evidence_tampering_is_rejected(case: Case, field: str, value: str | float) -> None:
    with pytest.raises(ValueError, match=r"Jev|Semantic"):
        run(case, {case.candidate.candidate_id: replace(evidence(case), **{field: value})})


def test_absent_candidate_and_changed_pair_are_rejected(case: Case) -> None:
    with pytest.raises(ValueError, match="absent candidate"):
        run(case, {"absent": evidence(case)})
    changed = replace(case, amendment=case.amendment.model_copy(update={"new_text": "other law"}))
    with pytest.raises(ValueError, match="different inputs"):
        run(changed, {case.candidate.candidate_id: evidence(case)})


def test_digest_preserves_default_and_binds_model_and_prompt(case: Case) -> None:
    legacy = (
        METHOD,
        ASSESSMENT_REVISION,
        case.model.model_dump(mode="json"),
        case.corpus.fingerprint,
        None,
        None,
        None,
    )
    before = hashlib.sha256(json.dumps(legacy, sort_keys=True).encode()).hexdigest()
    assert model_digest(case.model, case.corpus) == before
    configured = model_digest(case.model, case.corpus, jev_model=MODEL, jev_prompt_revision=PROMPT)
    assert configured != before
    assert configured != model_digest(
        case.model, case.corpus, jev_model=(MODEL[0], "changed"), jev_prompt_revision=PROMPT
    )
    assert configured != model_digest(
        case.model, case.corpus, jev_model=MODEL, jev_prompt_revision="changed"
    )
    assert not any(name.startswith("jev_") for name in case.run().signals)


@pytest.mark.parametrize(
    ("model", "prompt"),
    [
        (None, PROMPT),
        (MODEL, None),
        (MODEL, ""),
        (("", "rev"), PROMPT),
        (("model", ""), PROMPT),
    ],
)
def test_partial_or_blank_configuration_is_rejected(
    case: Case, model: tuple[str, str] | None, prompt: str | None
) -> None:
    with pytest.raises(ValueError, match="Jev"):
        model_digest(case.model, case.corpus, jev_model=model, jev_prompt_revision=prompt)


def test_semantics_context_and_jev_work_in_one_fitted_combiner(case: Case) -> None:
    names = (
        "lexical_overlap",
        "rare_phrase_overlap",
        "rarity_overlap",
        "alignment",
        "operation_agreement",
        "context_comparable",
        "negation_conflict",
        "modal_conflict",
        "quantity_conflict",
        "quoted_law_masked_chars",
        "background_z",
        "mutual_reciprocal_rank",
        "semantic_cosine",
        *NAMES,
    )
    model = fit_combiner(
        ((0.0,) * len(names), (1.0,) * len(names)),
        (False, True),
        names,
        training_id="train",
    )
    semantic = SemanticEvidence(0.75, *ENCODER, pair_digest(case.amendment, case.ask))
    rows = calculate_links(
        (case.candidate,),
        amendments={case.amendment.amendment_id: case.amendment},
        asks={case.ask.ask_id: case.ask},
        source_texts={case.ask.span.record_id: case.source},
        corpus=case.corpus,
        combiner=model,
        publication={},
        semantics={case.candidate.candidate_id: semantic},
        semantic_model=ENCODER,
        jev={case.candidate.candidate_id: evidence(case)},
        jev_model=MODEL,
        jev_prompt_revision=PROMPT,
    )
    assert len(rows) == 1
    result = rows[0]
    assert result.signals["semantic_cosine"] == 0.75
    assert result.signals["lexical_overlap"] == 1
    assert result.signals["rare_phrase_overlap"] > 0
    assert result.signals["jev_same_legal_change"] == 0.8
    assert result.signals["model_support"] == pytest.approx(
        model.score(tuple(result.signals[name] for name in names))
    )
    assert result.status == "unconfirmed"
    assert result.method_revision == model_digest(
        model,
        case.corpus,
        semantic_model=ENCODER,
        jev_model=MODEL,
        jev_prompt_revision=PROMPT,
    )


@pytest.mark.parametrize("side", ["before", "after"])
def test_changed_surrounding_context_rejects_stale_jev(case: Case, side: str) -> None:
    quote = case.source
    span = case.ask.span.model_copy(update={"start": 10, "end": 10 + len(quote)})
    contextual = replace(
        case,
        ask=case.ask.model_copy(update={"span": span}),
        source="x" * 10 + quote + "y" * 10,
    )
    recorded = evidence(contextual)
    assert run(contextual, {case.candidate.candidate_id: recorded}).status == "unconfirmed"
    modified_text = "z" * 10 + quote + "y" * 10 if side == "before" else "x" * 10 + quote + "z" * 10
    changed = replace(contextual, source=modified_text)
    assert changed.ask.span == contextual.ask.span
    assert len(changed.source) == len(contextual.source)
    with pytest.raises(ValueError, match="Jev source"):
        run(changed, {case.candidate.candidate_id: recorded})
