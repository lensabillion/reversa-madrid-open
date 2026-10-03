"""The harness: reproducible paired tests, leak-free out-of-fold scores, and its outputs."""

import math
import runpy
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from demo_fixture import write_dataset
from practice_fixture import labelled, practice_records

from influence.practice.__main__ import main
from influence.practice.folds import make_folds
from influence.practice.harness import (
    PracticeResults,
    ScorerContractError,
    SimulationSettings,
    evaluate,
    out_of_fold_scores,
    simulated_tests,
    write_atomically,
)
from influence.practice.labels import LabelledPair, PracticeDataError, PracticePair


def test_simulated_tests_are_reproducible_and_balanced() -> None:
    influenced = [True] * 40 + [False] * 35
    draws = simulated_tests(influenced, 20, 30, seed=7)
    assert draws == simulated_tests(influenced, 20, 30, seed=7)
    assert draws != simulated_tests(influenced, 20, 30, seed=8)
    for draw in draws:
        assert len(set(draw.members)) == 60
        assert all(influenced[index] for index in draw.members[:30])
        assert not any(influenced[index] for index in draw.members[30:])
        assert sorted(draw.tie_order) == list(range(60))


def test_simulated_tests_need_enough_of_each_class() -> None:
    with pytest.raises(PracticeDataError, match="needs 30 real pairs and 30 decoys"):
        simulated_tests([True] * 30 + [False] * 29, 1, 30, seed=0)


def _four_organizations() -> list[LabelledPair]:
    return [
        labelled(f"org{org}", f"{org}-{item}", f"{org}-{item}", item == 0, f"c{org}-{item}")
        for org in range(4)
        for item in range(2)
    ]


def test_each_pair_is_scored_once_in_its_test_fold_without_its_label() -> None:
    pairs = _four_organizations()
    plan = make_folds(pairs, 2)
    seen: list[str] = []

    def scorer(training: Sequence[LabelledPair], test: Sequence[PracticePair]) -> list[float]:
        # The test pairs' type carries no label; only training pairs do.
        assert all(isinstance(item, PracticePair) for item in test)
        assert all(isinstance(item, LabelledPair) for item in training)
        seen.extend(pair.candidate_id for pair in test)
        return [len(training) / 100] * len(test)

    scores = out_of_fold_scores(scorer, pairs, plan)
    assert sorted(seen) == sorted(item.pair.candidate_id for item in pairs)
    for fold in plan.folds:
        assert all(scores[index] == len(fold.train) / 100 for index in fold.test)


@pytest.mark.parametrize(
    ("returned", "message"),
    [
        ([0.5], "Expected 4 scores, got 1"),
        ([0.5, 0.5, 0.5, math.nan], "outside"),
        ([1.5] * 4, "outside"),
    ],
)
def test_scorer_contract_is_enforced(returned: list[float], message: str) -> None:
    pairs = _four_organizations()
    plan = make_folds(pairs, 2)
    with pytest.raises(ScorerContractError, match=message):
        out_of_fold_scores(lambda _training, _test: returned, pairs, plan)


def test_fold_metrics_are_none_where_a_fold_lacks_a_class() -> None:
    pairs = [labelled("real", "r", "r", True, "c1"), labelled("decoy", "d", "d", False, "c2")]
    plan = make_folds(pairs, 2)
    settings = SimulationSettings(
        draws=1,
        per_class=1,
        seed=0,
        generator="Python random.Random (Mersenne Twister)",
        top_k=1,
        recall_threshold=0.5,
    )
    draws = simulated_tests([True, False], 1, 1, seed=0)
    result = evaluate("toy", (0.9, 0.1), pairs, plan, draws, settings)
    assert result.full_set_auc == 1.0
    assert [(fold.auc, fold.recall) for fold in result.folds] == [(None, 1.0), (None, None)]


def _run(data: Path, out: Path, *extra: str) -> int:
    return main(["--data", str(data), "--out", str(out), "--draws", "50", "--seed", "3", *extra])


def test_full_run_writes_deterministic_results_that_match_the_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_dataset(tmp_path, practice_records())
    out = tmp_path / "results.json"
    assert _run(tmp_path, out) == 0
    first = out.read_text()
    results = PracticeResults.model_validate_json(first)
    assert (results.labels.positives, results.labels.weak_negatives) == (36, 36)
    assert results.labels.outcomes["unlabelled_never_checked"] == 1
    assert results.labels.outcomes["unlabelled_crowd_support"] == 1
    assert results.folds.grouping == "connected_components"
    # The fixture's copies repeat the amendment's edit and its decoys ask for another one,
    # so both scorers separate them perfectly.
    for scorer in results.scorers.values():
        assert scorer.draws.precision_at_top.mean == 1.0
        assert scorer.draws.auc.mean == 1.0
    assert all(set(row.scores) == set(results.scorers) for row in results.pairs)
    assert first.count('"candidate_id"') == len(results.pairs) == 72
    assert "36 positives, 36 weak negatives; 5 folds" in capsys.readouterr().out
    assert _run(tmp_path, out) == 0
    assert out.read_text() == first


def test_unusable_inputs_fail_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "results.json"
    assert _run(tmp_path / "missing", out) == 1
    write_dataset(tmp_path, practice_records(organizations=2, per_organization=4))
    assert _run(tmp_path, out, "--folds", "5") == 1
    assert _run(tmp_path, out, "--folds", "2") == 1
    errors = capsys.readouterr().err
    assert "2 independent groups cannot fill 5 folds" in errors
    assert "needs 30 real pairs and 30 decoys" in errors
    assert not out.exists()


@pytest.mark.parametrize(
    "options",
    [["--draws", "0"], ["--folds", "1"], ["--recall-threshold", "1.5"]],
)
def test_invalid_options_are_usage_errors(tmp_path: Path, options: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _run(tmp_path, tmp_path / "results.json", *options)
    assert exit_info.value.code == 2


def test_missing_output_directory_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _run(tmp_path, tmp_path / "absent" / "results.json")
    assert exit_info.value.code == 2


def test_failed_write_keeps_the_previous_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "results.json"
    target.write_text("previous")

    def fail(_self: Path, _target: Path) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        write_atomically(target, "new")
    assert target.read_text() == "previous"
    assert [path.name for path in tmp_path.iterdir()] == ["results.json"]


def test_module_runs_as_a_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_dataset(tmp_path, practice_records())
    out = tmp_path / "results.json"
    argv = ["influence.practice", "--data", str(tmp_path), "--out", str(out), "--draws", "5"]
    monkeypatch.setattr(sys, "argv", argv)
    # This file already imported the module; runpy warns about re-running a loaded module.
    monkeypatch.delitem(sys.modules, "influence.practice.__main__", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("influence.practice", run_name="__main__")
    assert exit_info.value.code == 0
    assert out.exists()
