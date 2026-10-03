"""The `influence submit` command end to end: exit status, streams and exact output bytes.

The golden pairs.csv holds scores that can be checked by hand: P01 shares 2 of 2 + 5
changed units (4/7), P,02 is identical (1), Ä-03 shares nothing (0) and P04 shares one
of 3 + 3 passage units (1/3). If scoring changes deliberately, regenerate it with
`uv run --directory backend --locked influence submit --pairs
tests/golden/submission/input.jsonl --out <tmp> --expected-pairs 4` and copy pairs.csv.
"""

import re
from pathlib import Path

import pytest

from influence.cli import main
from influence.schemas.submission import PairEvidence

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
