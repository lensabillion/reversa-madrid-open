"""The `influence` command end to end: exit status, streams and exact output bytes.

The golden pairs.csv holds scores that can be checked by hand: P01 shares 2 of 2 + 5
changed units (4/7), P,02 is identical (1), Ä-03 shares nothing (0) and P04 shares one
of 3 + 3 passage units (1/3). If scoring changes deliberately, regenerate it with
`uv run --directory backend --locked influence submit --pairs
tests/golden/submission/input.jsonl --out <tmp> --expected-pairs 4` and copy pairs.csv.
"""

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from influence import cli
from influence.cli import main
from influence.extraction.fetching import CachedFetcher
from influence.schemas.atlas import LawRecord, LayerCoverage, RunManifest, StageReceipt
from influence.schemas.submission import PairEvidence
from influence.services.collect import COLLECT_REVISION, CollectError, CollectResult

GOLDEN = Path(__file__).parent / "golden" / "submission"


def test_submit_writes_golden_pairs_csv_and_matching_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "new" / "out"
    status = main(
        [
            "submit",
            "--pairs",
            str(GOLDEN / "input.jsonl"),
            "--out",
            str(out),
            "--expected-pairs",
            "4",
        ]
    )
    captured = capsys.readouterr()
    assert status == 0
    assert captured.err == ""
    assert re.fullmatch(
        r"Scored 4 pairs in \d+\.\d\d s \(comparison modes: edits 1, passages 3\)\n"
        rf"pairs\.csv: {re.escape(str(out / 'pairs.csv'))}\n"
        rf"evidence:  {re.escape(str(out / 'pairs.evidence.jsonl'))}\n",
        captured.out,
    )
    assert (out / "pairs.csv").read_bytes() == (GOLDEN / "pairs.csv").read_bytes()
    evidence = [
        PairEvidence.model_validate_json(line)
        for line in (out / "pairs.evidence.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [item.pair_id for item in evidence] == ["P01", 'P,02 "quoted"', "Ä-03", "P04"]
    assert [item.influence_score for item in evidence] == [4 / 7, 1.0, 0.0, 1 / 3]
    assert [item.comparison.mode for item in evidence] == ["edits", *["passages"] * 3]
    assert all(item.comparison.limitations for item in evidence)


def test_invalid_input_exits_nonzero_and_keeps_previous_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text(
        (GOLDEN / "input.jsonl").read_text(encoding="utf-8") + "not json\n", encoding="utf-8"
    )
    out = tmp_path / "out"
    out.mkdir()
    (out / "pairs.csv").write_text("pair_id,influence_score\nOLD,0.5\n", encoding="utf-8")
    status = main(["submit", "--pairs", str(pairs), "--out", str(out), "--expected-pairs", "4"])
    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err == (
        "error: Invalid pairs input: 2 problem(s)\n"
        "  line 5: invalid JSON: Expecting value at column 1\n"
        "  expected 4 pairs (--expected-pairs), found 5\n"
        "Nothing was written. Fix the input (or its adapter) and rerun.\n"
    )
    assert [path.name for path in out.iterdir()] == ["pairs.csv"]
    assert (out / "pairs.csv").read_text(encoding="utf-8") == "pair_id,influence_score\nOLD,0.5\n"


def test_unwritable_output_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "a-file"
    out.write_text("", encoding="utf-8")
    pairs = str(GOLDEN / "input.jsonl")
    status = main(["submit", "--pairs", pairs, "--out", str(out), "--expected-pairs", "4"])
    captured = capsys.readouterr()
    assert status == 1
    assert captured.out == ""
    assert captured.err.startswith(f"error: cannot write outputs in {out}: ")
    assert captured.err.endswith(f"{out / 'pairs.csv'} was not replaced.\n")


@pytest.mark.parametrize(
    ("value", "message"), [("0", "must be at least 1, got 0"), ("sixty", "not an integer: 'sixty'")]
)
def test_expected_pairs_must_be_a_positive_integer(
    value: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["submit", "--pairs", "p.jsonl", "--out", "out", "--expected-pairs", value])
    assert caught.value.code == 2
    assert message in capsys.readouterr().err


# --- influence collect --------------------------------------------------------------------

STARTED = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
COVERAGE = (
    LayerCoverage(layer="metadata", status="complete"),
    LayerCoverage(layer="asks", status="partial", count=304, reason="Attachment limit: 5 of 259"),
)
LAW = LawRecord(
    procedure_id="2021/0106(COD)",
    title="Artificial Intelligence Act",
    status="completed",
    celex_final="32024R1689",
    coverage=COVERAGE,
)
STAGES = (
    StageReceipt(stage="metadata", status="reused", input_hash="a" * 64, seconds=0.25),
    StageReceipt(
        stage="asks",
        status="partial",
        input_hash="b" * 64,
        seconds=12.5,
        counts={"feedback": 304, "passages": 9},
        errors=("Attachment x not downloaded",),
    ),
)


class FakeCollect:
    """Stands in for the service: records what the adapter passed and answers as told."""

    def __init__(self, answer: Path | CollectError) -> None:
        self.answer = answer
        self.query: str | None = None
        self.options: dict[str, object] = {}

    def __call__(
        self,
        query: str,
        *,
        data_root: Path,
        fetcher: CachedFetcher,
        clock: Callable[[], datetime],
        code_revision: str,
        attachment_limit: int | None,
        hardware: str | None,
        progress: Callable[[str], None],
    ) -> CollectResult:
        self.query = query
        self.options = {
            "data_root": data_root,
            "cache": fetcher.cache.directory,
            "code_revision": code_revision,
            "attachment_limit": attachment_limit,
            "hardware": hardware,
            "clock_is_aware": clock().utcoffset() is not None,
        }
        progress("asks: running")
        if isinstance(self.answer, CollectError):
            raise self.answer
        manifest = RunManifest(
            run_id="run-1",
            query=query,
            procedure_id=LAW.procedure_id,
            status="complete",
            started_at=STARTED,
            completed_at=STARTED,
            code_revision=code_revision,
            stages=STAGES,
            coverage=COVERAGE,
        )
        return CollectResult(LAW, manifest, self.answer / "manifest.json", self.answer)


def test_collect_passes_the_options_to_the_service_and_prints_the_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeCollect(tmp_path / "laws" / "2021-0106-COD")
    monkeypatch.setattr(cli, "collect_law", fake)
    arguments = ["collect", "AI", "Act", "--data-root", str(tmp_path), "--attachment-limit", "5"]
    status = main([*arguments, "--code-revision", "abc123"])
    captured = capsys.readouterr()

    assert status == 0
    assert fake.query == "AI Act"
    assert fake.options["data_root"] == tmp_path
    assert fake.options["cache"] == tmp_path / "cache"
    assert fake.options["code_revision"] == "abc123"
    assert fake.options["attachment_limit"] == 5
    assert fake.options["clock_is_aware"] is True
    assert "logical CPUs" in str(fake.options["hardware"])
    assert captured.err == "asks: running\n"
    assert re.fullmatch(
        r"2021/0106\(COD\)  Artificial Intelligence Act  \(completed\)\n"
        r"proposal unknown, final act 32024R1689, no COM reference\n"
        r"Coverage:\n"
        r"  metadata              complete              -\n"
        r"  asks                  partial             304  Attachment limit: 5 of 259\n"
        r"Stages:\n"
        r"  metadata    reused        0\.25 s\n"
        r"  asks        partial      12\.50 s  feedback 304, passages 9\n"
        r"    error: Attachment x not downloaded\n"
        r"Collected in \d+\.\d\d s\n"
        rf"manifest: {re.escape(str(tmp_path / 'laws' / '2021-0106-COD' / 'manifest.json'))}\n",
        captured.out,
    )
    # pypdf's font warnings are silenced here, in the adapter, not in the service.
    assert logging.getLogger("pypdf").level == logging.ERROR


def test_collect_defaults_to_the_repository_data_and_every_attachment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeCollect(tmp_path)
    monkeypatch.setattr(cli, "collect_law", fake)
    assert main(["collect", "2021/0106(COD)"]) == 0
    capsys.readouterr()

    assert fake.query == "2021/0106(COD)"
    assert fake.options["data_root"] == Path(cli.__file__).resolve().parents[3] / "data"
    assert fake.options["attachment_limit"] is None
    assert str(fake.options["code_revision"]).startswith("influence-")
    assert str(fake.options["code_revision"]).endswith(f"+{COLLECT_REVISION}")


def test_collect_lists_the_choices_of_an_ambiguous_query_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    error = CollectError("'data' matches several procedures", ["2022/0047(COD)  Data Act"])
    monkeypatch.setattr(cli, "collect_law", FakeCollect(error))
    status = main(["collect", "data"])
    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert captured.err == (
        "asks: running\n"
        "error: 'data' matches several procedures\n"
        "  2022/0047(COD)  Data Act\n"
        "No manifest was published.\n"
    )


def test_collect_runs_the_real_service_and_reports_a_missing_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = main(["collect", "2021/0106(COD)", "--data-root", str(tmp_path)])
    captured = capsys.readouterr()

    assert status == 1
    assert captured.out == ""
    assert captured.err.startswith("error: The procedure catalog cannot be built or read: ")
    assert captured.err.endswith("No manifest was published.\n")
    assert not (tmp_path / "laws").exists()


def test_collect_rejects_a_limit_that_is_not_a_positive_integer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["collect", "AI Act", "--attachment-limit", "0"])
    assert caught.value.code == 2
    assert "must be at least 1, got 0" in capsys.readouterr().err
