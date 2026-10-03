"""Offline Jev practice preparation and evaluation; never calls a model or publishes links.

Run from backend with ``uv run --locked python -m benchmarks.jev_practice prepare
--data ../data/lobbyplag --out ../data/jev-evaluation``. Evaluate adds ``--inputs``
and ``--cache`` pointing at the frozen inputs and the gate3 runner output directory.
The optional ``--combiner`` compares a fitted lexical + four-Noul scorer out of fold.
Thresholds use even development folds only; odd folds are checked without tuning.
Clean-edit copy labels do not validate prose requests or causal influence.
"""

import argparse
import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import cast

from benchmarks.jev_gate3 import (
    CachedResult,
    PreparedCase,
    PreparedTrial,
    build_request,
    digest,
    key_for,
    load_ledger,
    load_trial,
    write,
)
from influence.extraction.files import write_bytes_atomic
from influence.practice.__main__ import PER_CLASS, TOP_K, lexical_scores
from influence.practice.folds import FoldPlan, make_folds
from influence.practice.harness import SimulationSettings, evaluate, simulated_tests
from influence.practice.labels import LabelledPair, PracticeSet, build_practice_set
from influence.repositories.lobbyplag import DemoRepository
from influence.services.calibration import fit_combiner, precision_report, select_threshold
from influence.services.jev import MODEL, JevRequest, NoulAnswer

FOLDS = 5
SEED = 0
DRAWS = 2000
FEATURES = (
    "lexical_overlap",
    "actual_request",
    "same_legal_change",
    "incompatible_legal_change",
    "shared_background",
)
CONTEXT_STATUS = (
    "Only this amendment's supplied original wording is available as local "
    "proposal context; no complete proposal document or surrounding submission "
    "context is supplied. submission_old and submission_new are the public "
    "source's legislative proposal edit, including explicit empty text for "
    "insertion/deletion; they are not inferred from ordinary prose."
)
CAVEATS = (
    "LobbyPlag copy-association labels are not entailment or causal-influence truth.",
    "100 negatives are weak crowd-rejected examples, not independently adjudicated negatives.",
    "One historical law and candidates preselected by a lexical matcher; these clean-edit "
    "results and cutoffs do not transfer to real consultation prose or reworded links.",
    "Even-fold threshold selection is development only, not an independent publication audit.",
    "Organization folds purge train/test text overlaps; duplicated texts can still occur "
    "between development and held-out test partitions. This is not a fresh-law audit.",
    "Noul values are raw support signals, not calibrated influence probabilities. "
    "Recall at 0.5 is a fixed legacy comparison metric, never a publication rule.",
    "No model selection, publication override or runtime activation occurs here.",
)


def prepared(data: Path) -> tuple[PreparedTrial, PracticeSet, FoldPlan]:
    """Reuse the public loader and grouped folds, preserving both sides of every edit."""
    practice = build_practice_set(DemoRepository.load(data))
    plan = make_folds(practice.pairs, FOLDS)
    cases: list[PreparedCase] = []
    for item in practice.pairs:
        pair = item.pair
        cases.append(
            PreparedCase(
                case_id=pair.candidate_id,
                family="legal-change-v1",
                state={
                    "submission_old": pair.submission.old,
                    "submission_new": pair.submission.new,
                    "preceding_context": "",
                    "following_context": "",
                    "amendment_old": pair.amendment.old,
                    "amendment_new": pair.amendment.new,
                    "proposal_text": pair.amendment.old,
                    "proposal_context_status": CONTEXT_STATUS,
                },
                metadata={
                    "candidate_id": pair.candidate_id,
                    "amendment_id": pair.amendment_id,
                    "proposal_id": pair.proposal_id,
                    "source_dataset": "LobbyPlag public snapshot",
                },
            )
        )
    return (
        PreparedTrial(
            source_hashes={path.name: digest(path) for path in sorted(data.glob("*.json"))},
            cases=cases,
        ),
        practice,
        plan,
    )


def prepare(data: Path, output: Path) -> None:
    """Write requests and separate labels atomically; no labels enter the model state."""
    trial, practice, plan = prepared(data)
    inputs = output / "lobbyplag-inputs.json"
    # Preserve the original preparation's bytes, so existing experiment provenance stays valid.
    write_bytes_atomic(
        inputs,
        (json.dumps(trial.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n").encode(),
    )
    labels: list[dict[str, object]] = [
        {
            "case_id": item.pair.candidate_id,
            "positive": item.influenced,
            "label_source": item.source,
            "crowd_checks": item.crowd_checks,
            "crowd_yes_votes": item.crowd_yes_votes,
            "document_language": item.document_language,
            "organization_id": item.pair.organization_id,
        }
        for item in practice.pairs
    ]
    write(
        output / "lobbyplag-labels.json",
        {
            "schema_version": "jev-lobbyplag-labels-1",
            "inputs_sha256": digest(inputs),
            "provenance": CAVEATS[0],
            "labels": labels,
            "fold_grouping": plan.grouping,
            "folds": [
                {
                    "fold_id": number,
                    **{
                        role: [
                            practice.pairs[i].pair.candidate_id
                            for i in cast(tuple[int, ...], getattr(fold, role))
                        ]
                        for role in ("train", "test", "purged")
                    },
                }
                for number, fold in enumerate(plan.folds)
            ],
            "excluded": dict(practice.excluded),
            "identical_inputs": asdict(practice.identical_inputs),
        },
    )
    write(
        output / "lobbyplag-preparation.json",
        {
            "schema_version": "jev-lobbyplag-preparation-1",
            "input_sha256": digest(inputs),
            "labels_sha256": digest(output / "lobbyplag-labels.json"),
            "source_hashes": trial.source_hashes,
            "sorted_case_ids": [case.case_id for case in trial.cases],
            "cases": len(practice.pairs),
            "positives": sum(item.influenced for item in practice.pairs),
            "weak_negatives": sum(not item.influenced for item in practice.pairs),
            "requests_sent": 0,
        },
    )


def cached_features(
    trial: PreparedTrial, cache: Path
) -> tuple[dict[str, tuple[float, ...]], dict[str, str]]:
    """Validate every request/response join and ledger hash; partial runs cannot look complete."""
    ledger = load_ledger(cache)
    features: dict[str, tuple[float, ...]] = {}
    hashes: dict[str, str] = {}
    for case in trial.cases:
        key = key_for(case)
        entry = ledger.entries.get(key)
        if entry is None or entry.status != "complete":
            raise ValueError(f"Missing complete cached response for {case.case_id}")
        path = cache / "results" / f"{key}.json"
        if digest(path) != entry.result_sha256:
            raise ValueError(f"Cached response hash mismatch for {case.case_id}")
        request = JevRequest.model_validate_json((cache / "requests" / f"{key}.json").read_bytes())
        if request != build_request(case):
            raise ValueError(f"Cached request differs from frozen inputs for {case.case_id}")
        result = CachedResult.model_validate_json(path.read_bytes())
        if result.request_sha256 != key or set(result.response.answers) != set(FEATURES[1:]):
            raise ValueError(f"Cached response has wrong request/questions for {case.case_id}")
        values: list[float] = []
        for name in FEATURES[1:]:
            answer = result.response.answers[name]
            if not isinstance(answer, NoulAnswer):
                raise ValueError(f"Expected native Noul for {case.case_id}/{name}")
            values.append(answer.noul)
        features[case.case_id] = tuple(values)
        hashes[key] = digest(path)
    return features, hashes


def fitted_scores(
    rows: Sequence[Sequence[float]],
    pairs: Sequence[LabelledPair],
    plan: FoldPlan,
    *,
    development_only: bool,
) -> tuple[list[float], list[dict[str, object]]]:
    """O(F*I*n*p) fixed logistic fits; no test labels or text-overlapping rows enter a fit.

    Threshold-selection scores restrict every fit to even development folds. Development
    test folds are cross-fitted; odd held-out labels are never read by those fits.
    """
    development = {i for n, fold in enumerate(plan.folds) if n % 2 == 0 for i in fold.test}
    scores = [0.0] * len(pairs)
    fits: list[dict[str, object]] = []
    for number, fold in enumerate(plan.folds):
        train = [i for i in fold.train if not development_only or i in development]
        ids = [pairs[i].pair.candidate_id for i in train]
        training_id = hashlib.sha256(json.dumps(ids).encode()).hexdigest()
        model = fit_combiner(
            [rows[i] for i in train],
            [pairs[i].influenced for i in train],
            FEATURES,
            training_id=training_id,
        )
        for i in fold.test:
            scores[i] = model.score(rows[i])
        fits.append({"fold": number, "training_ids": ids, "model": model.model_dump(mode="json")})
    return scores, fits


def threshold_report(
    scores: Sequence[float], pairs: Sequence[LabelledPair], plan: FoldPlan
) -> dict[str, object]:
    """Freeze a cutoff using even folds, then count odd-fold results without tuning."""
    development = [i for n, fold in enumerate(plan.folds) if n % 2 == 0 for i in fold.test]
    held_out = [i for n, fold in enumerate(plan.folds) if n % 2 == 1 for i in fold.test]
    selection = select_threshold(
        [scores[i] for i in development],
        [pairs[i].influenced for i in development],
        development_id="lobbyplag-even-folds-0-2-4-v1",
        minimum_precision=0.90,
        minimum_samples=30,
    )
    report = None
    if selection.threshold is not None:
        report = precision_report(
            [scores[i] for i in held_out],
            [pairs[i].influenced for i in held_out],
            threshold=selection.threshold,
        ).model_dump(mode="json")
    return {
        "selection": selection.model_dump(mode="json"),
        "held_out": report,
        "development_case_ids": [pairs[i].pair.candidate_id for i in development],
        "held_out_case_ids": [pairs[i].pair.candidate_id for i in held_out],
    }


def evaluate_cached(
    data: Path, inputs: Path, cache: Path, output: Path, *, combiner: bool
) -> dict[str, object]:
    """Compare complete cached outputs on fixed folds/draws; O(D*m log m) plus optional fits."""
    expected, practice, plan = prepared(data)
    trial = load_trial(inputs)
    if trial != expected:
        raise ValueError(
            "Frozen inputs differ from public-source preparation; do not mix experiments"
        )
    features, response_hashes = cached_features(trial, cache)
    pairs = practice.pairs
    lexical = lexical_scores((), [item.pair for item in pairs])
    rows = [
        (score, *features[item.pair.candidate_id])
        for score, item in zip(lexical, pairs, strict=True)
    ]
    scores = {"lexical-delta-v1": lexical, "jev-same-legal-change-v1": [row[2] for row in rows]}
    fits: dict[str, object] = {}
    threshold_scores = dict(scores)
    if combiner:
        scores["lexical-jev-combiner-v1"], fits["comparison_oof"] = fitted_scores(
            rows, pairs, plan, development_only=False
        )
        threshold_scores["lexical-jev-combiner-v1"], fits["threshold_development_only"] = (
            fitted_scores(rows, pairs, plan, development_only=True)
        )
    settings = SimulationSettings(
        draws=DRAWS,
        per_class=PER_CLASS,
        seed=SEED,
        generator="Python random.Random (Mersenne Twister)",
        top_k=TOP_K,
        recall_threshold=0.5,
    )
    draws = simulated_tests([item.influenced for item in pairs], DRAWS, PER_CLASS, SEED)
    backend = Path(__file__).resolve().parents[1]
    source_files = (
        "benchmarks/jev_practice.py",
        "benchmarks/jev_gate3.py",
        "src/influence/services/jev.py",
        "src/influence/practice/labels.py",
        "src/influence/practice/folds.py",
        "src/influence/practice/harness.py",
        "src/influence/practice/metrics.py",
        "src/influence/practice/__main__.py",
        "src/influence/services/comparison.py",
        "src/influence/services/scoring.py",
        "src/influence/services/calibration.py",
    )
    report: dict[str, object] = {
        "schema_version": "jev-practice-evaluation-1",
        "model": MODEL,
        "source_hashes": trial.source_hashes,
        "input_sha256": digest(inputs),
        "implementation_sha256": {name: digest(backend / name) for name in source_files},
        "requests_sha256": {case.case_id: key_for(case) for case in trial.cases},
        "responses_sha256": response_hashes,
        "cases": len(pairs),
        "positives": sum(item.influenced for item in pairs),
        "weak_negatives": sum(not item.influenced for item in pairs),
        "grouping": plan.grouping,
        "features": FEATURES,
        "settings": settings.model_dump(mode="json"),
        "development_folds": [0, 2, 4],
        "held_out_folds": [1, 3],
        "threshold_rule": (
            "Lowest observed complete-tie cutoff; development Wilson95% "
            "lower>=0.90 and n>=30. No retuning on odd folds."
        ),
        "scorers": {
            name: evaluate(name, values, pairs, plan, draws, settings).model_dump(mode="json")
            for name, values in scores.items()
        },
        "thresholds": {
            name: threshold_report(values, pairs, plan) for name, values in threshold_scores.items()
        },
        "fits": fits,
        "pair_scores": [
            {
                "case_id": item.pair.candidate_id,
                **{name: values[i] for name, values in scores.items()},
            }
            for i, item in enumerate(pairs)
        ],
        "caveats": CAVEATS,
        "automatic_publication": False,
    }
    write(output, report)
    return report


def summarize(report: dict[str, object], report_path: Path, output: Path) -> None:
    """Keep fixed results and provenance compact; the full ignored report retains all fits."""
    hashes = cast(dict[str, str], report["responses_sha256"])
    thresholds = cast(dict[str, dict[str, object]], report["thresholds"])
    summary = {
        key: report[key]
        for key in (
            "schema_version",
            "model",
            "source_hashes",
            "input_sha256",
            "implementation_sha256",
            "cases",
            "positives",
            "weak_negatives",
            "grouping",
            "features",
            "settings",
            "development_folds",
            "held_out_folds",
            "threshold_rule",
            "scorers",
            "caveats",
            "automatic_publication",
        )
    }
    summary.update(
        {
            "artifact": "Compact generated summary; full report kept in ignored data",
            "full_report_sha256": digest(report_path),
            "response_provenance": {
                "unique_responses": len(hashes),
                "sha256_of_sorted_response_hash_manifest": hashlib.sha256(
                    json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "manifest_location": (
                    "Full report responses_sha256 maps request hashes to response file hashes"
                ),
            },
            "thresholds": {
                name: {key: value for key, value in row.items() if key in ("selection", "held_out")}
                for name, row in thresholds.items()
            },
            "interpretation": {
                "activation": "None; this artifact grants no publication approval.",
                "precision_target": (
                    "0.90 is the prespecified development selection target. "
                    "Held-out intervals describe uncertainty; they do not establish that precision "
                    "and are not a newly invented held-out acceptance rule."
                ),
                "selection": (
                    "Compare top-20 precision, recall, AUC and held-out intervals "
                    "together; a higher AUC alone does not establish safer "
                    "published links."
                ),
                "reworded_floor": (
                    "The plan's separate 0.80 reworded precision floor was not "
                    "tested: these are copy labels without a validated reworded "
                    "stratum. Do not retune to 0.80 after observing results or "
                    "transfer clean-edit cutoffs to prose."
                ),
                "combiner_threshold_fit": (
                    "Separate development-only fits, excluding odd-fold labels, "
                    "supply threshold-selection and held-out scores. Full OOF "
                    "comparison scores use each original purged training fold."
                ),
            },
            "reproduce": (
                "From backend: uv run --locked python -m benchmarks.jev_practice "
                "evaluate --data PATH/lobbyplag --inputs PATH/lobbyplag-inputs.json "
                "--cache PATH/jev-run --out PATH/practice-report.json --combiner "
                "--summary evaluation/jev-gate3-evaluation.json. Requires archived "
                "raw cached responses; no new API call."
            ),
        }
    )
    write(output, summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "evaluate"))
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--combiner", action="store_true")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    data, output = cast(Path, args.data), cast(Path, args.out)
    if args.mode == "prepare":
        prepare(data, output)
        print(f"Prepared public inputs and separate labels in {output}")
    else:
        inputs, cache = cast(Path | None, args.inputs), cast(Path | None, args.cache)
        if inputs is None or cache is None:
            parser.error("evaluate requires --inputs and --cache")
        result = evaluate_cached(data, inputs, cache, output, combiner=cast(bool, args.combiner))
        summary = cast(Path | None, args.summary)
        if summary is not None:
            summarize(result, output, summary)
        print(
            json.dumps({key: result[key] for key in ("cases", "scorers", "thresholds")}, indent=2)
        )


if __name__ == "__main__":
    main()
