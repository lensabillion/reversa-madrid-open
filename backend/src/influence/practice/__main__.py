"""Measure the baseline scorers on LobbyPlag's labelled pairs and write the results.

Run from the repository root:

    uv run --directory backend --locked python -m influence.practice \
        --data /absolute/path/to/data/lobbyplag --out evaluation/practice-results.json

The JSON is a pure function of the input files and the options: it records the inputs'
SHA-256 digests, not their paths, and no timing. Timing is printed instead.
"""

import argparse
import hashlib
import platform
import sys
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import cast

from influence.practice.folds import make_folds
from influence.practice.harness import (
    PracticeResults,
    Scorer,
    SimulationSettings,
    evaluate,
    folds_report,
    label_report,
    out_of_fold_scores,
    pair_rows,
    render,
    simulated_tests,
    write_atomically,
)
from influence.practice.labels import (
    LabelledPair,
    PracticeDataError,
    PracticePair,
    build_practice_set,
)
from influence.repositories.lobbyplag import (
    DatasetInvalidError,
    DatasetUnavailableError,
    DemoRepository,
)
from influence.schemas.comparison import ComparisonRequest, InputText
from influence.services.comparison import compare_texts

DATA_FILES = ("amendments", "proposals", "plags", "documents", "lobbyists")
PER_CLASS = 30
TOP_K = 20
HEADER = ("P@20", "p10", "recall", "p10", "AUC", "p10")


def lexical_scores(_training: Sequence[LabelledPair], test: Sequence[PracticePair]) -> list[float]:
    """Main's comparison service in edits mode; unsupervised, so training pairs go unused."""
    return [
        compare_texts(
            ComparisonRequest(
                amendment=InputText(old=pair.amendment.old, new=pair.amendment.new),
                submission=InputText(old=pair.submission.old, new=pair.submission.new),
            )
        ).score
        for pair in test
    ]


def stored_match_scorer(repository: DemoRepository) -> Scorer:
    """LobbyPlag's own matcher score: a sanity baseline that does not exist for new pairs."""

    def scores(_training: Sequence[LabelledPair], test: Sequence[PracticePair]) -> list[float]:
        return [repository.candidates[pair.candidate_id].match for pair in test]

    return scores


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m influence.practice",
        description="Measure scorers on simulated 30 + 30 hidden tests from LobbyPlag.",
    )
    parser.add_argument("--data", type=Path, required=True, help="LobbyPlag snapshot directory")
    parser.add_argument("--out", type=Path, required=True, help="Results JSON to (re)write")
    parser.add_argument("--seed", type=int, default=0, help="Seed of the simulated tests")
    parser.add_argument("--draws", type=int, default=2000, help="Number of simulated tests")
    parser.add_argument("--folds", type=int, default=5, help="Number of grouped folds")
    parser.add_argument(
        "--recall-threshold",
        type=float,
        default=0.5,
        help="Score at which a pair counts as found; open organizer question D5",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    data, out = cast("Path", args.data), cast("Path", args.out)
    seed, draws, k = cast("int", args.seed), cast("int", args.draws), cast("int", args.folds)
    threshold = cast("float", args.recall_threshold)
    if draws < 1 or k < 2 or not 0 <= threshold <= 1:
        parser.error("need --draws >= 1, --folds >= 2 and 0 <= --recall-threshold <= 1")
    if not out.parent.is_dir():
        parser.error(f"output directory does not exist: {out.parent}")
    started = perf_counter()
    try:
        repository = DemoRepository.load(data)
        hashes = {f"{name}.json": _sha256(data / f"{name}.json") for name in DATA_FILES}
        practice = build_practice_set(repository)
        plan = make_folds(practice.pairs, k)
        tests = simulated_tests([p.influenced for p in practice.pairs], draws, PER_CLASS, seed)
    except (OSError, DatasetUnavailableError, DatasetInvalidError, PracticeDataError) as error:
        cause = f" ({error.__cause__})" if error.__cause__ else ""
        print(f"error: {error}{cause}", file=sys.stderr)
        return 1
    loaded = perf_counter()
    settings = SimulationSettings(
        draws=draws,
        per_class=PER_CLASS,
        seed=seed,
        generator="Python random.Random (Mersenne Twister)",
        top_k=TOP_K,
        recall_threshold=threshold,
    )
    scorers: dict[str, tuple[str, Scorer]] = {
        "lexical-delta-v1": (
            "Main's comparison service (influence.services.comparison.compare_texts) on clean "
            "edits: amendment and proposal old/new wording, both originals known",
            lexical_scores,
        ),
        "lobbyplag-stored-match": (
            "LobbyPlag's stored match score (plags.json match), from the matcher that proposed "
            "every candidate; a sanity baseline, unavailable for the hidden test",
            stored_match_scorer(repository),
        ),
    }
    scores: dict[str, tuple[float, ...]] = {}
    timings: dict[str, float] = {}
    for name, (_, scorer) in scorers.items():
        scoring_started = perf_counter()
        scores[name] = out_of_fold_scores(scorer, practice.pairs, plan)
        timings[name] = perf_counter() - scoring_started
    results = PracticeResults(
        kind="practice-harness-results-v1",
        input_sha256=hashes,
        labels=label_report(
            practice,
            len(repository.candidates),
            repository.duplicate_candidate_rows,
            repository.merged_crowd_tallies,
        ),
        folds=folds_report(plan, practice.pairs),
        simulated_tests=settings,
        scorers={
            name: evaluate(description, scores[name], practice.pairs, plan, tests, settings)
            for name, (description, _) in scorers.items()
        },
        pairs=pair_rows(practice.pairs, plan, scores),
    )
    write_atomically(out, render(results))
    finished = perf_counter()
    labels = results.labels
    print(
        f"{labels.positives} positives, {labels.weak_negatives} weak negatives; "
        f"{k} folds ({plan.grouping}); {draws} simulated tests of {PER_CLASS} + {PER_CLASS}, "
        f"seed {seed}; recall threshold {threshold}"
    )
    print(f"{'scorer':<24}" + "".join(f"{column:>8}" for column in HEADER) + f"{'full AUC':>10}")
    for name, result in results.scorers.items():
        draw = result.draws
        print(
            f"{name:<24}{draw.precision_at_top.mean:>8.3f}{draw.precision_at_top.p10:>8.3f}"
            f"{draw.recall.mean:>8.3f}{draw.recall.p10:>8.3f}{draw.auc.mean:>8.3f}"
            f"{draw.auc.p10:>8.3f}{result.full_set_auc:>10.3f}"
        )
    scoring = ", ".join(f"{name} {seconds:.3f} s" for name, seconds in timings.items())
    print(
        f"Wrote {out}. Load, label and fold {loaded - started:.3f} s; scoring {scoring}; "
        f"total {finished - started:.3f} s on {platform.machine()} {platform.system()}, "
        f"Python {platform.python_version()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
