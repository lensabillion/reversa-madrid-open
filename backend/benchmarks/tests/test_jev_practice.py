"""Offline integrity and held-out separation checks for the optional practice benchmark."""

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from benchmarks.jev_gate3 import (
    CachedResult,
    Entry,
    Ledger,
    PreparedCase,
    PreparedTrial,
    build_request,
    digest,
    key_for,
    write,
)
from benchmarks.jev_practice import FEATURES, cached_features, fitted_scores, threshold_report
from influence.practice.folds import Fold, FoldPlan, make_folds
from influence.practice.labels import LabelledPair, PracticePair
from influence.repositories.lobbyplag import RawText
from influence.services.jev import MODEL, JevResult, NoulAnswer, Usage


def pair(index: int, positive: bool) -> LabelledPair:
    return LabelledPair(
        pair=PracticePair(
            candidate_id=str(index),
            amendment_id=f"a{index}",
            proposal_id=f"p{index}",
            organization_id=f"org{index // 8}",
            amendment=RawText(old=f"old{index}", new=f"new{index}"),
            submission=RawText(old=f"sold{index}", new=f"snew{index}"),
        ),
        source="volunteer_verified" if positive else "crowd_rejected",
        crowd_checks=1,
        crowd_yes_votes=int(positive),
        document_language="en",
    )


def trial() -> PreparedTrial:
    return PreparedTrial(
        source_hashes={},
        cases=[
            PreparedCase(
                case_id="deletion",
                family="legal-change-v1",
                state={
                    "submission_old": "The reporting duty applies.",
                    "submission_new": "",
                    "preceding_context": "",
                    "following_context": "",
                    "amendment_old": "The reporting duty applies.",
                    "amendment_new": "",
                    "proposal_text": None,
                    "proposal_context_status": "Local edit only",
                },
                metadata={"label_must_not_be_sent": True},
            )
        ],
    )


def save_cache(path: Path, value: PreparedTrial) -> str:
    case = value.cases[0]
    key = key_for(case)
    result = CachedResult(
        request_sha256=key,
        completed_at="2026-10-03T00:00:00Z",
        elapsed_seconds=1.0,
        response=JevResult(
            model=MODEL,
            answers={name: NoulAnswer(type="noul", noul=0.8) for name in FEATURES[1:]},
            usage=Usage(input_tokens=1, output_tokens=0),
        ),
    )
    write(path / "requests" / f"{key}.json", build_request(case))
    result_path = path / "results" / f"{key}.json"
    write(result_path, result)
    write(
        path / "ledger.json",
        Ledger(
            entries={
                key: Entry(
                    case_id=case.case_id,
                    status="complete",
                    reserved_usd=0.01,
                    actual_cost_usd=0.001,
                    result_sha256=digest(result_path),
                )
            }
        ),
    )
    return key


def test_deletion_and_labels_remain_separate_in_validated_cache(tmp_path: Path) -> None:
    value = trial()
    key = save_cache(tmp_path, value)
    features, hashes = cached_features(value, tmp_path)
    assert features == {"deletion": (0.8, 0.8, 0.8, 0.8)}
    assert key in hashes
    request = build_request(value.cases[0])
    assert request.state == value.cases[0].state
    assert "label_must_not_be_sent" not in request.model_dump_json()


def test_incomplete_and_tampered_caches_fail(tmp_path: Path) -> None:
    value = trial()
    with pytest.raises(ValueError, match="Missing complete"):
        cached_features(value, tmp_path)
    key = save_cache(tmp_path, value)
    (tmp_path / "results" / f"{key}.json").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        cached_features(value, tmp_path)


def test_request_mutation_cannot_reuse_response(tmp_path: Path) -> None:
    value = trial()
    key = save_cache(tmp_path, value)
    changed = value.cases[0].model_copy(
        update={"state": {**value.cases[0].state, "submission_new": "keep duty"}}
    )
    write(tmp_path / "requests" / f"{key}.json", build_request(changed))
    with pytest.raises(ValueError, match="Cached request differs"):
        cached_features(value, tmp_path)


def test_held_out_failures_do_not_retune_development_cutoff() -> None:
    pairs = [pair(i, i < 40) for i in range(70)]
    plan = FoldPlan(
        grouping="organizations_with_purge",
        components=(),
        folds=(
            Fold(test=tuple(range(50)), train=tuple(range(50, 70)), purged=()),
            Fold(test=tuple(range(50, 70)), train=tuple(range(50)), purged=()),
        ),
    )
    scores = [0.8] * 40 + [0.2] * 10 + [0.99] * 20
    report = threshold_report(scores, pairs, plan)
    assert cast(dict[str, object], report["selection"])["threshold"] == 0.8
    assert cast(dict[str, object], report["held_out"])["correct"] == 0
    assert cast(dict[str, object], report["held_out"])["selected"] == 20
    changed = [
        replace(item, source="volunteer_verified") if i >= 50 else item
        for i, item in enumerate(pairs)
    ]
    assert threshold_report(scores, changed, plan)["selection"] == report["selection"]


def test_development_only_fits_never_use_held_out_labels() -> None:
    pairs = [pair(i, i % 2 == 0) for i in range(80)]
    plan = make_folds(pairs, 5)
    held = {i for n, fold in enumerate(plan.folds) if n % 2 == 1 for i in fold.test}
    rows = [
        (0.9, 0.9, 0.8, 0.1, 0.1) if item.influenced else (0.1, 0.8, 0.2, 0.8, 0.7)
        for item in pairs
    ]
    scores, fits = fitted_scores(rows, pairs, plan, development_only=True)
    changed = [
        replace(item, source="crowd_rejected" if item.influenced else "volunteer_verified")
        if i in held
        else item
        for i, item in enumerate(pairs)
    ]
    other, other_fits = fitted_scores(rows, changed, plan, development_only=True)
    assert other == scores
    assert other_fits == fits
    assert min(scores[i] for i in range(80) if i % 2 == 0) > max(
        scores[i] for i in range(80) if i % 2
    )
