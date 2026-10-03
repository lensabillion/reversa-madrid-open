"""Fused retrieval: rank fusion, recall and cap per retriever, labelled shortlist precision."""

import runpy
import sys
from pathlib import Path

import pytest
from demo_fixture import write_dataset
from hypothesis import given
from hypothesis import strategies as st
from practice_fixture import Records, practice_records

from influence.practice.fused import (
    KS,
    FusedReport,
    FusedRow,
    PrecisionRow,
    main,
    measure_fused,
    render,
)
from influence.practice.labels import PracticeDataError, build_practice_set
from influence.repositories.lobbyplag import DemoRepository
from influence.services.retrieval import fuse_rankings


def test_fusion_orders_by_summed_reciprocal_rank_and_keeps_first_seen_on_ties() -> None:
    assert fuse_rankings([["a", "b", "c"], ["b", "a", "d"]]) == ["a", "b", "c", "d"]


def test_an_item_both_lists_like_beats_one_only_a_single_list_likes() -> None:
    assert fuse_rankings([["x", "y"], ["z", "y"]]) == ["y", "x", "z"]


def test_nothing_to_fuse_is_empty() -> None:
    assert fuse_rankings([]) == []
    assert fuse_rankings([[], []]) == []


@given(st.lists(st.lists(st.sampled_from("abcdef"), unique=True, max_size=6), max_size=3))
def test_fusion_returns_every_distinct_item_exactly_once(rankings: list[list[str]]) -> None:
    fused = fuse_rankings(rankings)
    assert sorted(fused) == sorted({item for ranking in rankings for item in ranking})


def _records() -> Records:
    """Four verified amendments; `a0-0` and its proposal are deletions, so it has no whole text.

    `a0-2` also has a crowd-rejected candidate, so its shortlist holds all three kinds of
    proposal: verified, weakly rejected and unlabelled.
    """
    records = practice_records(organizations=2, per_organization=4)
    next(a for a in records["amendments"] if a["uid"] == "a0-0")["text"] = [
        {"lang": "en", "old": "Article 0-0 requires consent.", "new": ""}
    ]
    next(p for p in records["proposals"] if p["uid"] == "p0-0")["text"] = {
        "old": "Article 0-0 requires consent.",
        "new": "",
    }
    records["plags"].append(
        {
            "uid": "c-weak",
            "amendment": "a0-2",
            "proposal": "p1-0",
            "verified": False,
            "match": 0.5,
            "processing": {"checked": 1, "verified": 0},
        }
    )
    return records


def _report(tmp_path: Path, records: Records) -> FusedReport:
    write_dataset(tmp_path, records)
    repository = DemoRepository.load(tmp_path)
    report, seconds = measure_fused(
        repository, build_practice_set(repository), {"x.json": "0" * 64}
    )
    assert set(seconds) == {"delta", "whole_text", "rrf"}
    assert all(value >= 0 for value in seconds.values())
    return report


def _row(report: FusedReport, subset: str, retriever: str) -> FusedRow:
    return next(r for r in report.rows if (r.subset, r.retriever) == (subset, retriever))


def _precision(report: FusedReport, retriever: str, k: int) -> PrecisionRow:
    return next(p for p in report.precision if (p.retriever, p.k) == (retriever, k))


def test_whole_text_cannot_search_a_deletion_but_the_fused_shortlists_fall_back(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path, _records())
    assert (report.verified_pairs, report.amendments, report.amendments_without_whole_text) == (
        4,
        4,
        1,
    )
    delta = _row(report, "all_verified_pairs", "delta")
    whole = _row(report, "all_verified_pairs", "whole_text")
    # The deletion amendment is a miss for the whole-text query, so it never reaches 95%.
    assert whole.recall_at["50"] == pytest.approx(0.75)
    assert whole.cap_for_target is None
    assert whole.mean_shortlist_size_at_cap is None
    for name in ("rrf", "union"):
        fused = _row(report, "all_verified_pairs", name)
        assert all(fused.recall_at[str(k)] >= delta.recall_at[str(k)] for k in KS)
        assert fused.recall_at_depth == 1.0


def test_both_queries_and_the_fusions_are_compared_on_the_same_pairs(tmp_path: Path) -> None:
    report = _report(tmp_path, _records())
    rows = [r for r in report.rows if r.subset == "amendment_has_new_text"]
    assert [r.retriever for r in rows] == ["delta", "whole_text", "rrf", "union"]
    assert {r.pairs for r in rows} == {3}
    assert len(report.rows) == 8


def test_cap_is_the_smallest_k_reaching_the_target_and_union_costs_more_candidates(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path, _records())
    rrf = _row(report, "amendment_has_new_text", "rrf")
    union = _row(report, "amendment_has_new_text", "union")
    assert rrf.cap_for_target is not None
    assert union.cap_for_target is not None
    assert rrf.recall_at_depth >= 0.95
    # Merging two lists of k returns between k and 2k distinct proposals; rrf returns k.
    assert rrf.mean_shortlist_size_at_cap == pytest.approx(rrf.cap_for_target)
    assert union.mean_shortlist_size_at_cap is not None
    assert union.cap_for_target <= union.mean_shortlist_size_at_cap <= 2 * union.cap_for_target
    assert rrf.mrr is not None
    assert union.mrr is None


def test_precision_splits_the_shortlist_into_verified_weak_and_unlabelled(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path, _records())
    assert len(report.precision) == 8
    delta = _precision(report, "delta", 20)
    assert delta.amendments == 4
    # Four verified pairs and one crowd-rejected one, over four amendments.
    assert delta.mean_verified == pytest.approx(1.0)
    assert delta.mean_weakly_rejected == pytest.approx(0.25)
    assert delta.mean_unlabelled > 0
    total = delta.mean_verified + delta.mean_weakly_rejected + delta.mean_unlabelled
    assert total == pytest.approx(delta.mean_candidates)
    assert delta.labelled_precision == pytest.approx(1.0 / 1.25)


def test_when_no_query_can_run_every_shortlist_is_empty_and_precision_is_unknown(
    tmp_path: Path,
) -> None:
    records = _records()
    for amendment in records["amendments"]:
        if amendment["uid"] in {"a0-0", "a0-2", "a1-0", "a1-2"}:
            amendment["text"] = [
                {"lang": "en", "old": "Article requires consent.", "new": "word " * 13_000}
            ]
    report = _report(tmp_path, records)
    for row in report.rows:
        assert row.recall_at_depth == 0.0
        assert row.cap_for_target is None
    assert all(p.labelled_precision is None and p.mean_candidates == 0 for p in report.precision)


def test_no_verified_pairs_is_an_error(tmp_path: Path) -> None:
    records = practice_records(organizations=2, per_organization=4)
    for plag in records["plags"]:
        plag["verified"] = False
        plag["processing"] = {"checked": 1, "verified": 0}
    with pytest.raises(PracticeDataError, match="No verified pairs"):
        _report(tmp_path, records)


def _run(data: Path, out: Path) -> int:
    return main(["--data", str(data), "--out", str(out)])


def test_cli_writes_deterministic_json_with_input_digests(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_dataset(tmp_path, _records())
    out = tmp_path / "fused.json"
    assert _run(tmp_path, out) == 0
    first = out.read_text(encoding="utf-8")
    report = FusedReport.model_validate_json(first)
    assert report.kind == "fused-retrieval-v1"
    assert set(report.input_sha256) == {
        "amendments.json",
        "proposals.json",
        "plags.json",
        "documents.json",
        "lobbyists.json",
    }
    assert first == render(report)
    printed = capsys.readouterr().out
    assert "4 verified pairs, 4 amendments" in printed
    assert "labelled precision" in printed
    assert "Mean per query" in printed
    assert _run(tmp_path, out) == 0
    assert out.read_text(encoding="utf-8") == first


def test_cli_prints_unknown_precision_and_missing_caps_when_nothing_can_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records = _records()
    for amendment in records["amendments"]:
        if amendment["uid"] in {"a0-0", "a0-2", "a1-0", "a1-2"}:
            amendment["text"] = [
                {"lang": "en", "old": "Article requires consent.", "new": "word " * 13_000}
            ]
    write_dataset(tmp_path, records)
    assert _run(tmp_path, tmp_path / "fused.json") == 0
    printed = capsys.readouterr().out
    assert "precision n/a" in printed
    assert "cap none size      -" in printed


def test_cli_fails_cleanly_on_unusable_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "fused.json"
    assert _run(tmp_path / "missing", out) == 1
    assert not out.exists()
    assert "error:" in capsys.readouterr().err


def test_cli_rejects_a_missing_output_directory(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _run(tmp_path, tmp_path / "absent" / "fused.json")
    assert exit_info.value.code == 2


def test_module_runs_as_a_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_dataset(tmp_path, _records())
    out = tmp_path / "fused.json"
    monkeypatch.setattr(
        sys, "argv", ["influence.practice.fused", "--data", str(tmp_path), "--out", str(out)]
    )
    monkeypatch.delitem(sys.modules, "influence.practice.fused", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("influence.practice.fused", run_name="__main__")
    assert exit_info.value.code == 0
    assert out.exists()
