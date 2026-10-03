"""Reproduce the consolidated-plan combiner comparison on fixed LobbyPlag folds.

Run with --help. Semantic scores must come from the pinned backend/models runner.
This development evaluation is NOT the independent 2019+ publication audit.
"""

import argparse
import hashlib
import json
import platform
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import cast

from benchmarks.jev_gate3 import digest, key_for, load_trial
from benchmarks.jev_practice import cached_features, prepared
from influence.practice.__main__ import lexical_scores
from influence.practice.folds import make_folds
from influence.practice.harness import (
    SimulationSettings,
    evaluate,
    folds_report,
    out_of_fold_scores,
    simulated_tests,
    write_atomically,
)
from influence.practice.labels import LabelledPair, PracticePair, build_practice_set
from influence.repositories.lobbyplag import DemoRepository
from influence.schemas.scoring import TextChange
from influence.services.calibration import fit_combiner, select_threshold
from influence.services.evaluation_artifacts import ArtifactKind, load_model_features
from influence.services.jev import MODEL
from influence.services.ranking_signals import RankedPair, background_signals, feature_vector
from influence.services.signals import SignalCorpus, pair_signals

DETERMINISTIC = (
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
)
CONTEXT = (
    "background_z",
    "forward_reciprocal_rank",
    "reverse_reciprocal_rank",
    "mutual_reciprocal_rank",
)
JUDGE = ("entailment_score", "contradiction_score")
JEV = (
    "jev_actual_request",
    "jev_same_legal_change",
    "jev_incompatible_legal_change",
    "jev_shared_background",
)


def jev_features(
    data: Path, inputs: Path, cache: Path, pairs: Sequence[PracticePair]
) -> tuple[dict[str, dict[str, float]], dict[str, object]]:
    """Join cached atomic legal questions to the exact public-source practice preparation."""
    expected, practice, _ = prepared(data)
    trial = load_trial(inputs)
    if trial != expected or [item.pair for item in practice.pairs] != list(pairs):
        raise ValueError("Jev inputs differ from the current public-source practice preparation")
    features, response_hashes = cached_features(trial, cache)
    rows: dict[str, dict[str, float]] = {
        identifier: dict(zip(JEV, values, strict=True)) for identifier, values in features.items()
    }
    provenance: dict[str, object] = {
        "model": MODEL,
        "inputs_sha256": digest(inputs),
        "ledger_sha256": digest(cache / "ledger.json"),
        "source_hashes": trial.source_hashes,
        "request_sha256_by_candidate": {case.case_id: key_for(case) for case in trial.cases},
        "response_sha256_by_request": response_hashes,
        "features": JEV,
        "role": "Four cached legal-question Noul signals; not an NLI class distribution.",
    }
    return rows, provenance


def feature_variants(*, semantic: bool, judge: bool, jev: bool) -> dict[str, tuple[str, ...]]:
    """Keep the incumbent ablations while adding Jev to the existing full feature family."""
    variants: dict[str, tuple[str, ...]] = {
        "deterministic": DETERMINISTIC,
        "deterministic_context": (*DETERMINISTIC, *CONTEXT),
    }
    if semantic:
        variants["deterministic_semantic"] = (*DETERMINISTIC, "semantic_cosine")
        variants["all_signals"] = (*DETERMINISTIC, *CONTEXT, "semantic_cosine")
    if judge:
        variants["deterministic_judge"] = (*DETERMINISTIC, *JUDGE)
        variants["deterministic_context_judge"] = (*DETERMINISTIC, *CONTEXT, *JUDGE)
        if semantic:
            variants["all_signals_judge"] = (*DETERMINISTIC, *CONTEXT, "semantic_cosine", *JUDGE)
    if jev:
        variants["deterministic_context_jev"] = (*DETERMINISTIC, *CONTEXT, *JEV)
        if judge:
            variants["deterministic_context_judge_jev"] = (*DETERMINISTIC, *CONTEXT, *JUDGE, *JEV)
        if semantic:
            variants["all_signals_jev"] = (
                *DETERMINISTIC,
                *CONTEXT,
                "semantic_cosine",
                *(JUDGE if judge else ()),
                *JEV,
            )
    return variants


def signal_rows(
    pairs: Sequence[PracticePair], corpus: SignalCorpus, model_features: dict[str, dict[str, float]]
) -> list[dict[str, float]]:
    rows = [
        pair_signals(
            TextChange(old=pair.amendment.old, new=pair.amendment.new),
            TextChange(old=pair.submission.old, new=pair.submission.new),
            corpus,
        )
        for pair in pairs
    ]
    background = background_signals(
        [
            RankedPair(
                pair.candidate_id, pair.amendment_id, pair.proposal_id, row["lexical_overlap"]
            )
            for pair, row in zip(pairs, rows, strict=True)
        ]
    )
    for pair, row in zip(pairs, rows, strict=True):
        row.update(background[pair.candidate_id])
        row.update(model_features.get(pair.candidate_id, {}))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--semantic", type=Path)
    parser.add_argument("--judge", type=Path)
    parser.add_argument("--jev-inputs", type=Path, help="Frozen Jev public-source practice inputs")
    parser.add_argument("--jev-cache", type=Path, help="Completed Jev request/response cache")
    parser.add_argument(
        "--model-inputs", type=Path, help="Frozen inputs.json used by all model artifacts"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data, out = cast("Path", args.data), cast("Path", args.out)
    semantic_path = cast("Path | None", args.semantic)
    judge_path = cast("Path | None", args.judge)
    inputs_path = cast("Path | None", args.model_inputs)
    jev_inputs = cast("Path | None", args.jev_inputs)
    jev_cache = cast("Path | None", args.jev_cache)
    if (jev_inputs is None) != (jev_cache is None):
        parser.error("--jev-inputs and --jev-cache must be supplied together")
    if (semantic_path or judge_path) and inputs_path is None:
        parser.error("--model-inputs is required with --semantic or --judge")
    started = perf_counter()
    service_dir = Path(__file__).resolve().parents[1] / "src/influence/services"
    implementation_hashes = {
        name: hashlib.sha256((service_dir / name).read_bytes()).hexdigest()
        for name in ("scoring.py", "signals.py", "ranking_signals.py", "calibration.py")
    }
    implementation_hashes["calculation_plan.py"] = digest(Path(__file__))
    if jev_inputs is not None:
        implementation_hashes["jev.py"] = digest(service_dir / "jev.py")
        for name in ("jev_gate3.py", "jev_practice.py"):
            implementation_hashes[name] = digest(Path(__file__).with_name(name))
    repository = DemoRepository.load(data)
    practice = build_practice_set(repository)
    source_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(data.glob("*.json"))
    }
    model_features: dict[str, dict[str, float]] = {}
    model_artifacts: dict[str, object] = {}
    artifact_paths: tuple[tuple[ArtifactKind, Path | None], ...] = (
        ("semantic", semantic_path),
        ("judge", judge_path),
    )
    for kind, artifact_path in artifact_paths:
        if artifact_path is not None and inputs_path is not None:
            artifact = load_model_features(
                artifact_path,
                kind=kind,
                inputs_path=inputs_path,
                source_hashes=source_hashes,
                pairs=[item.pair for item in practice.pairs],
            )
            model_artifacts[kind] = dict(artifact.provenance)
            for identifier, values in artifact.features.items():
                model_features.setdefault(identifier, {}).update(values)
    if jev_inputs is not None and jev_cache is not None:
        features, provenance = jev_features(
            data, jev_inputs, jev_cache, [item.pair for item in practice.pairs]
        )
        model_artifacts["jev"] = provenance
        for identifier, values in features.items():
            model_features.setdefault(identifier, {}).update(values)
    plan = make_folds(practice.pairs, 5)
    draws = simulated_tests([pair.influenced for pair in practice.pairs], 2000, 30, 0)
    settings = SimulationSettings(
        draws=2000,
        per_class=30,
        seed=0,
        generator="Python random.Random (Mersenne Twister)",
        top_k=20,
        recall_threshold=0.5,
    )
    scores = {"lexical_baseline": out_of_fold_scores(lexical_scores, practice.pairs, plan)}
    fitted: dict[str, list[dict[str, object]]] = {}
    variants = feature_variants(
        semantic=semantic_path is not None, judge=judge_path is not None, jev=jev_inputs is not None
    )
    for name, names in variants.items():
        fits: list[dict[str, object]] = []

        def scorer(
            training: Sequence[LabelledPair],
            test: Sequence[PracticePair],
            feature_names: tuple[str, ...] = names,
            fitted_models: list[dict[str, object]] = fits,
        ) -> list[float]:
            corpus = SignalCorpus(
                [
                    text
                    for pair in training
                    for text in (pair.pair.amendment.new, pair.pair.submission.new)
                ]
            )
            training_pairs = [item.pair for item in training]
            train_rows = signal_rows(training_pairs, corpus, model_features)
            test_rows = signal_rows(test, corpus, model_features)
            training_id = hashlib.sha256(
                "\n".join(pair.candidate_id for pair in training_pairs).encode()
            ).hexdigest()
            model = fit_combiner(
                [feature_vector(row, feature_names) for row in train_rows],
                [item.influenced for item in training],
                feature_names,
                training_id=training_id,
                max_iterations=20_000,
            )
            fitted_models.append(model.model_dump(mode="json"))
            return [model.score(feature_vector(row, feature_names)) for row in test_rows]

        scores[name] = out_of_fold_scores(scorer, practice.pairs, plan)
        fitted[name] = fits
    labels = [item.influenced for item in practice.pairs]
    metrics = {
        name: evaluate(name, result, practice.pairs, plan, draws, settings).model_dump(mode="json")
        for name, result in scores.items()
    }
    thresholds = {
        name: select_threshold(
            result,
            labels,
            development_id=(
                "LobbyPlag grouped OOF development; independent publication audit pending"
            ),
            minimum_precision=0.9,
            minimum_samples=30,
        ).model_dump(mode="json")
        for name, result in scores.items()
    }
    report = {
        "kind": "consolidated-calculation-development-v1",
        "implementation_sha256": implementation_hashes,
        "runtime": {
            "elapsed_seconds": perf_counter() - started,
            "python": platform.python_version(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "input_sha256": source_hashes,
        "model_artifacts": model_artifacts,
        "folds": folds_report(plan, practice.pairs).model_dump(mode="json"),
        "settings": settings.model_dump(mode="json"),
        "metrics": metrics,
        "development_thresholds": thresholds,
        "threshold_role": (
            "Pooled out-of-fold diagnostic across five fits; "
            "not a deployable cutoff for any single fitted model."
        ),
        "selection": {
            "incumbent": "lexical_baseline",
            "promoted": None,
            "policy": (
                "Retain all paired metrics. Precision-first comparison requires independent "
                "evaluation and a frozen model/corpus before publication audit; "
                "no automatic promotion."
            ),
        },
        "fold_models": fitted,
        "pairs": [
            {
                "candidate_id": pair.pair.candidate_id,
                "label_source": pair.source,
                "scores": {name: result[index] for name, result in scores.items()},
            }
            for index, pair in enumerate(practice.pairs)
        ],
        "limitations": [
            "One historical law; crowd-rejected negatives are weak labels.",
            "Feature weights and rarity statistics fit only on each purged training fold.",
            "Background ranks use observed fold pools, not every possible pair in the law.",
            "Development thresholds need a separate 2019+ blind audit; no probability calibration.",
            "English cues and semantic cosine do not establish legal equivalence.",
            "Judge features use full new text and generic English NLI; they are experimental "
            "signals, not verified entailment or legal verdicts.",
            "Jev features, when enabled, are separate actual-request, same-change, incompatible-"
            "change and shared-background Noul answers. Clean-edit practice labels do not "
            "validate real consultation prose; these signals never activate publication.",
            "Balanced 30-positive/30-negative panel precision is not estimated live publication "
            "precision; recall at numeric 0.5 uses different score scales.",
            "OOF threshold selection is diagnostic and combines five fitted score distributions, "
            "not one frozen deployable model.",
        ],
    }
    write_atomically(out, json.dumps(report, indent=2, sort_keys=True) + "\n")
    for name, metric in metrics.items():
        print(name, json.dumps(metric["draws"], sort_keys=True))
    print(
        f"Wrote {out}; {perf_counter() - started:.3f}s; "
        f"{platform.machine()} {platform.system()}; Python {platform.python_version()}"
    )


if __name__ == "__main__":
    main()
