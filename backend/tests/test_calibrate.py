"""Calibration: a fixed threshold rule, a leak-free combiner, and a deterministic report."""

import runpy
import sys
from pathlib import Path

import pytest
from demo_fixture import write_dataset
from practice_fixture import labelled, practice_records

from influence.practice.calibrate import (
    FEATURES,
    GRID,
    MIN_PAIRS,
    CalibrationReport,
    Proposal,
    _direction,  # pyright: ignore[reportPrivateUsage]
    _print,  # pyright: ignore[reportPrivateUsage]
    _proposal,  # pyright: ignore[reportPrivateUsage]
    calibrate,
    choose_threshold,
    combiner_scores,
    counts,
    fit_logistic,
    main,
    render,
    signals,
    tier_proposals,
    wilson_interval,
)
from influence.practice.labels import PracticePair
from influence.repositories.lobbyplag import DemoRepository, RawText
from influence.schemas.scoring import ChangeSpan


def _span(operation: str, text: str) -> ChangeSpan:
    return ChangeSpan.model_validate(
        {"operation": operation, "start": 0, "end": len(text), "text": text}
    )


def _pair(amendment: tuple[str, str], submission: tuple[str, str]) -> PracticePair:
    return PracticePair(
        candidate_id="c",
        amendment_id="a",
        proposal_id="p",
        organization_id="o",
        amendment=RawText(old=amendment[0], new=amendment[1]),
        submission=RawText(old=submission[0], new=submission[1]),
    )


def test_wilson_known_values_and_pinned_endpoints() -> None:
    low, high = wilson_interval(8, 10)
    assert (round(low, 3), round(high, 3)) == (0.490, 0.943)
    assert wilson_interval(0, 0) == (0.0, 1.0)
    assert wilson_interval(0, 3)[0] == 0.0
    assert wilson_interval(3, 3)[1] == 1.0


@pytest.mark.parametrize(
    ("spans", "expected"),
    [
        ([_span("insert", "shall keep, at least")], "stricter"),
        ([_span("insert", "may (optionally)")], "weaker"),
        ([_span("delete", "may")], "stricter"),
        ([_span("delete", "shall")], "weaker"),
        ([_span("insert", "the widget")], "unknown"),
        ([_span("insert", "shall"), _span("insert", "may")], "unknown"),
        ([], "unknown"),
    ],
)
def test_direction_is_read_only_from_obligation_cues(
    spans: list[ChangeSpan], expected: str
) -> None:
    assert _direction(spans) == expected


def test_signals_describe_a_copy_a_short_edit_and_opposite_directions() -> None:
    copy = signals(
        _pair(
            ("Keep logs.", "Keep logs for six months."), ("Keep logs.", "Keep logs for six months.")
        )
    )
    assert dict(zip(FEATURES, copy, strict=True))["lexical_overlap"] == 1.0
    assert all(0.0 <= value <= 1.0 for value in copy)
    swap = dict(
        zip(
            FEATURES,
            signals(
                _pair(("It shall apply.", "It may apply."), ("It shall apply.", "It may apply."))
            ),
            strict=True,
        )
    )
    assert (swap["short_edit"], swap["direction_agrees"], swap["direction_opposes"]) == (1, 1, 0)
    opposed = dict(
        zip(
            FEATURES,
            signals(
                _pair(("It shall apply.", "It may apply."), ("It may apply.", "It shall apply."))
            ),
            strict=True,
        )
    )
    assert (opposed["direction_agrees"], opposed["direction_opposes"]) == (0, 1)
    negated = dict(
        zip(
            FEATURES,
            signals(
                _pair(
                    ("Keep logs.", "Keep logs for years."),
                    ("Keep logs.", "Do not keep logs for years."),
                )
            ),
            strict=True,
        )
    )
    assert negated["negation_conflict"] == 1


def test_logistic_regression_separates_and_is_deterministic() -> None:
    rows = [(0.0, 0.0), (0.1, 1.0), (0.9, 0.0), (1.0, 1.0)]
    labels = [False, False, True, True]
    weights = fit_logistic(rows, labels)
    assert weights == fit_logistic(rows, labels)
    assert weights[0] > 0
    one_class = fit_logistic(rows, [True] * 4)
    assert len(one_class) == 3
    assert one_class[-1] > 0


def test_combiner_scores_stay_in_the_unit_range_and_ignore_test_labels() -> None:
    training = [
        labelled("o", f"{i}", f"{i}", influenced=i % 2 == 0, candidate=f"c{i}") for i in range(8)
    ]
    test = [item.pair for item in training[:3]]
    scores = combiner_scores(training, test)
    assert len(scores) == 3
    assert all(0.0 <= score <= 1.0 for score in scores)


def test_counts_and_threshold_choice() -> None:
    assert counts([0.2], [True], 0.5).precision is None
    scores = [0.9] * 30 + [0.4] * 10
    labels = [True] * 30 + [False] * 10
    chosen = choose_threshold(scores, labels, floor=0.8)
    assert chosen is not None
    assert counts(scores, labels, chosen).pairs >= MIN_PAIRS
    assert choose_threshold(scores, labels, floor=1.0) is None
    assert GRID[0] == 0.0
    assert GRID[-1] == 1.0


def test_a_proposal_is_none_when_no_threshold_clears_the_floor() -> None:
    scores = [0.9] * 30
    labels = [False] * 30
    found = _proposal("copied", 0.9, scores, labels, list(range(30)), [])
    assert found.threshold is None
    assert found.development is None
    ok = _proposal("copied", 0.8, [0.9] * 30, [True] * 30, list(range(30)), [])
    assert ok.threshold is not None
    assert ok.development is not None
    assert ok.held_out == counts([], [], ok.threshold)
    assert ok.below is None


def test_counts_can_stop_below_an_upper_cut() -> None:
    scores = [0.2, 0.5, 0.75, 0.9]
    labels = [False, True, True, True]
    assert counts(scores, labels, 0.5).pairs == 3
    band = counts(scores, labels, 0.3, below=0.75)
    assert (band.pairs, band.positives) == (1, 1)


def test_the_reworded_tier_is_chosen_on_its_own_band_not_on_the_copies_above_it() -> None:
    # Review finding: the reworded cut was chosen on every pair at or above it, copies
    # included. Here 60 correct copies at 0.9 lift a band of 20 pairs at 0.5 that is right
    # only 5 times: counted together they clear 0.80 (65 of 80); the band alone (5 of 20)
    # never does, so the reworded tier gets no threshold.
    scores = [0.9] * 60 + [0.5] * 20
    labels = [True] * 60 + [True] * 5 + [False] * 15
    together = choose_threshold(scores, labels, floor=0.7)
    assert together is not None
    assert together <= 0.5
    copied, reworded = tier_proposals(scores, labels, list(range(80)), [])
    assert copied.threshold is not None
    assert 0.5 < copied.threshold <= 0.9
    assert copied.below is None
    assert reworded.below == copied.threshold
    assert reworded.threshold is None
    assert reworded.development is None


def test_a_clean_band_below_the_copied_cut_gets_its_own_threshold() -> None:
    # 40 sure copies at 0.9, a band of 200 at 0.5 that is right 176 times (0.88), and 40
    # misses at 0.1; each entry is doubled so the even (development) and odd (held-out)
    # indices see the same data. Copies and band together (216 of 240, 0.90) miss the copied
    # floor, so the copied cut sits above the band, which then clears the reworded floor alone.
    unique = [(0.9, True)] * 40 + [(0.5, True)] * 176 + [(0.5, False)] * 24 + [(0.1, False)] * 40
    scores = [score for score, _ in unique for _ in range(2)]
    labels = [label for _, label in unique for _ in range(2)]
    development, held_out = list(range(0, len(scores), 2)), list(range(1, len(scores), 2))
    copied, reworded = tier_proposals(scores, labels, development, held_out)
    assert copied.threshold is not None
    assert 0.5 < copied.threshold <= 0.9
    assert reworded.threshold is not None
    assert 0.1 < reworded.threshold <= 0.5
    assert reworded.development is not None
    assert reworded.held_out is not None
    # Only the 0.5 band is counted, never the copies above it.
    assert (reworded.development.pairs, reworded.development.positives) == (200, 176)
    assert reworded.held_out == reworded.development


def test_no_grid_threshold_at_or_above_the_upper_cut_is_tried() -> None:
    assert choose_threshold([0.9] * 30, [True] * 30, floor=0.5, below=0.0) is None


def _report(tmp_path: Path) -> CalibrationReport:
    write_dataset(tmp_path, practice_records())
    return calibrate(
        DemoRepository.load(tmp_path),
        {"x.json": "0" * 64},
        seed=3,
        draws=50,
        folds=5,
        recall_threshold=0.5,
    )


def test_the_report_compares_both_scorers_on_the_same_folds(tmp_path: Path) -> None:
    report = _report(tmp_path)
    assert set(report.scorers) == {"lexical-delta-v1", "logistic-combiner-v1"}
    assert (report.positives, report.weak_negatives) == (36, 36)
    assert report.development_folds == (0, 2, 4)
    assert report.held_out_folds == (1, 3)
    lexical, combiner = report.scorers.values()
    assert len(lexical.folds) == len(combiner.folds) == 5
    for rows in report.tables.values():
        pairs = [row.all_pairs.pairs for row in rows]
        assert pairs == sorted(pairs, reverse=True)
        assert len(rows) == 9
    for tiers in report.proposals.values():
        assert [tier.tier for tier in tiers] == ["copied", "reworded"]
        assert tiers[0].floor > tiers[1].floor
        assert (tiers[0].below, tiers[1].below) == (None, tiers[0].threshold)
    assert report.kind == "link-calibration-v2"
    assert set(report.combiner_weights_all_pairs) == {*FEATURES, "bias"}
    assert report.rule
    assert report.caveats


def test_print_covers_a_missing_threshold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _report(tmp_path)
    none = Proposal(
        tier="copied",
        floor=0.9,
        min_pairs=MIN_PAIRS,
        threshold=None,
        below=None,
        development=None,
        held_out=None,
    )
    changed = report.model_copy(update={"proposals": {"lexical-delta-v1": (none,)}})
    _print(changed)
    printed = capsys.readouterr().out
    assert "no threshold reaches the floor" in printed
    _print(report)
    assert "held out" in capsys.readouterr().out


def _run(data: Path, out: Path, *extra: str) -> int:
    return main(["--data", str(data), "--out", str(out), "--draws", "50", "--seed", "3", *extra])


def test_cli_writes_deterministic_json_with_digests(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_dataset(tmp_path, practice_records())
    out = tmp_path / "calibration.json"
    assert _run(tmp_path, out) == 0
    first = out.read_text(encoding="utf-8")
    report = CalibrationReport.model_validate_json(first)
    assert first == render(report)
    assert set(report.input_sha256) == {
        "amendments.json",
        "proposals.json",
        "plags.json",
        "documents.json",
        "lobbyists.json",
    }
    assert "36 positives, 36 weak negatives" in capsys.readouterr().out
    assert _run(tmp_path, out) == 0
    assert out.read_text(encoding="utf-8") == first


def test_cli_fails_cleanly_on_unusable_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "calibration.json"
    assert _run(tmp_path / "missing", out) == 1
    assert not out.exists()
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "options",
    [["--draws", "0"], ["--folds", "1"], ["--recall-threshold", "1.5"]],
)
def test_invalid_options_are_usage_errors(tmp_path: Path, options: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--data", str(tmp_path), "--out", str(tmp_path / "c.json"), *options])
    assert exit_info.value.code == 2


def test_missing_output_directory_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _run(tmp_path, tmp_path / "absent" / "calibration.json")
    assert exit_info.value.code == 2


def test_module_runs_as_a_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_dataset(tmp_path, practice_records())
    out = tmp_path / "calibration.json"
    argv = [
        "influence.practice.calibrate",
        "--data",
        str(tmp_path),
        "--out",
        str(out),
        "--draws",
        "5",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delitem(sys.modules, "influence.practice.calibrate", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("influence.practice.calibrate", run_name="__main__")
    assert exit_info.value.code == 0
    assert out.exists()
