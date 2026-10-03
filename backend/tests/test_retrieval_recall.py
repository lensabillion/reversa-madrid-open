"""Retrieval recall: the right proposal must be in the shortlist, and the report says so."""

import runpy
import sys
from pathlib import Path

import pytest
from demo_fixture import write_dataset
from practice_fixture import Records, practice_records

from influence.practice.labels import PracticeDataError, build_practice_set
from influence.practice.recall import KS, RecallReport, RecallRow, main, measure_recall, render
from influence.repositories.lobbyplag import DemoRepository


def _records() -> Records:
    """Two organizations, four verified copies. `a0-0` and its proposal are both deletions."""
    records = practice_records(organizations=2, per_organization=4)
    next(a for a in records["amendments"] if a["uid"] == "a0-0")["text"] = [
        {"lang": "en", "old": "Article 0-0 requires consent.", "new": ""}
    ]
    next(p for p in records["proposals"] if p["uid"] == "p0-0")["text"] = {
        "old": "Article 0-0 requires consent.",
        "new": "",
    }
    # A decoy proposal with no text at all can never be retrieved.
    next(p for p in records["proposals"] if p["uid"] == "p0-1")["text"] = {"old": "", "new": ""}
    return records


def _report(tmp_path: Path, records: Records) -> RecallReport:
    write_dataset(tmp_path, records)
    repository = DemoRepository.load(tmp_path)
    return measure_recall(repository, build_practice_set(repository), {"x.json": "0" * 64})


def _row(report: RecallReport, corpus: str, query: str, subset: str) -> RecallRow:
    return next(
        row for row in report.rows if (row.corpus, row.query, row.subset) == (corpus, query, subset)
    )


def test_a_deletion_proposal_is_findable_only_when_indexed_by_what_it_deletes(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path, _records())
    assert report.verified_pairs == 4
    only_new = _row(report, "new_text_only", "delta", "all_verified_pairs")
    with_deleted = _row(report, "new_or_deleted_text", "delta", "all_verified_pairs")
    # Three copies are found at rank 1; the deletion pair is lost without the deleted wording.
    assert only_new.recall_at["5"] == pytest.approx(0.75)
    assert with_deleted.recall_at["5"] == 1.0
    # The extra pair also adds reciprocal rank, so the mean rises.
    assert 0 < only_new.mrr < with_deleted.mrr <= 1.0


def test_both_queries_are_compared_on_the_same_pairs(tmp_path: Path) -> None:
    report = _report(tmp_path, _records())
    delta = _row(report, "new_or_deleted_text", "delta", "amendment_has_new_text")
    whole = _row(report, "new_or_deleted_text", "whole_text", "amendment_has_new_text")
    # The deletion amendment has no new text, so it leaves this subset for every row.
    assert delta.pairs == whole.pairs == 3
    assert delta.recall_at == whole.recall_at
    assert len(report.rows) == 6


def test_pool_sizes_and_chance_recall(tmp_path: Path) -> None:
    report = _report(tmp_path, _records())
    # Eight proposals: one is empty, one is a deletion that only the second corpus holds.
    assert report.corpus_passages == {"new_text_only": 6, "new_or_deleted_text": 7}
    assert report.proposals_with_no_text == 1
    assert report.chance_recall_at["5"] == pytest.approx(5 / 7)
    assert report.chance_recall_at["10"] == 1.0
    assert tuple(int(k) for k in report.chance_recall_at) == KS


def test_an_amendment_with_two_verified_proposals_is_searched_once_and_counted_twice(
    tmp_path: Path,
) -> None:
    records = _records()
    records["plags"].append(
        {
            "uid": "c-extra",
            "amendment": "a0-2",
            "proposal": "p1-0",
            "verified": True,
            "match": 0.9,
            "processing": {"checked": 0, "verified": 0},
        }
    )
    report = _report(tmp_path, records)
    row = _row(report, "new_or_deleted_text", "delta", "all_verified_pairs")
    assert (report.verified_pairs, row.pairs) == (5, 5)
    # Both of the amendment's proposals share its changed words, and the pool is smaller
    # than k, so all five pairs are found.
    assert row.recall_at["50"] == 1.0


def test_a_query_that_cannot_run_counts_as_a_miss(tmp_path: Path) -> None:
    records = _records()
    next(a for a in records["amendments"] if a["uid"] == "a1-0")["text"] = [
        {"lang": "en", "old": "Article 1-0 requires consent.", "new": "word " * 13_000}
    ]
    report = _report(tmp_path, records)
    row = _row(report, "new_or_deleted_text", "delta", "all_verified_pairs")
    assert row.query_errors == 1
    assert row.recall_at["50"] < 1.0


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
    out = tmp_path / "recall.json"
    assert _run(tmp_path, out) == 0
    first = out.read_text(encoding="utf-8")
    report = RecallReport.model_validate_json(first)
    assert report.kind == "retrieval-recall-v1"
    assert set(report.input_sha256) == {
        "amendments.json",
        "proposals.json",
        "plags.json",
        "documents.json",
        "lobbyists.json",
    }
    assert first == render(report)
    printed = capsys.readouterr().out
    assert "4 verified pairs" in printed
    assert "new_or_deleted_text" in printed
    assert _run(tmp_path, out) == 0
    assert out.read_text(encoding="utf-8") == first


def test_cli_fails_cleanly_on_unusable_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "recall.json"
    assert _run(tmp_path / "missing", out) == 1
    assert not out.exists()
    assert "error:" in capsys.readouterr().err


def test_cli_rejects_a_missing_output_directory(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _run(tmp_path, tmp_path / "absent" / "recall.json")
    assert exit_info.value.code == 2


def test_module_runs_as_a_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_dataset(tmp_path, _records())
    out = tmp_path / "recall.json"
    monkeypatch.setattr(
        sys, "argv", ["influence.practice.recall", "--data", str(tmp_path), "--out", str(out)]
    )
    monkeypatch.delitem(sys.modules, "influence.practice.recall", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("influence.practice.recall", run_name="__main__")
    assert exit_info.value.code == 0
    assert out.exists()
