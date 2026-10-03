"""The submission service: every input problem at once, exact outputs, nothing partial."""

import csv
import errno
import io
import json
import math
import os
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from influence.schemas.comparison import ComparisonResult
from influence.schemas.submission import PairEvidence, SubmissionPair
from influence.services.submission import (
    EVIDENCE_JSONL,
    PAIRS_CSV,
    SubmissionError,
    check_scores,
    format_score,
    parse_pairs,
    read_pairs,
    render_pairs_csv,
    score_pairs,
    write_submission,
)

# derandomize fixes the seed, so a failure replays identically on every machine; no
# example database is written into the tree; a deadline would make results depend on
# machine speed.
PROPERTY = settings(derandomize=True, database=None, deadline=None)


def pair(pair_id: str, amendment: str = "retain data", submission: str = "retain data") -> str:
    return json.dumps(
        {
            "pair_id": pair_id,
            "amendment": {"old": None, "new": amendment},
            "submission": {"old": None, "new": submission},
        },
        ensure_ascii=False,
    )


def problems_of(data: bytes, expected_pairs: int) -> tuple[str, ...]:
    with pytest.raises(SubmissionError) as caught:
        parse_pairs(data, expected_pairs)
    return caught.value.problems


def test_reader_reports_every_problem_with_line_and_pair_id() -> None:
    lines = [
        pair("P1"),
        '{"pair_id": "P2", "amendment": {"old": null, "new": "x"}',
        "   ",
        "[]",
        json.dumps({"pair_id": "P5", "amendment": {"old": None, "new": "x"}}),
        pair("P6", amendment="x" * 12_001),
        pair("P7", submission="word " * 801),
        pair(" P8"),
        pair("P1"),
        pair("P5"),
        json.dumps({"amendment": {"old": None, "new": "x"}, "submission": {"old": "", "new": "x"}}),
    ]
    assert problems_of("\n".join(lines).encode(), expected_pairs=12) == (
        "line 2: invalid JSON: Expecting ',' delimiter at column 57",
        "line 3: blank; each line must hold one JSON object",
        "line 4: record: Input should be a valid dictionary or instance of SubmissionPair",
        "line 5 (pair_id 'P5'): submission: Field required",
        "line 6 (pair_id 'P6'): amendment.new: String should have at most 12000 characters",
        "line 7 (pair_id 'P7'): submission: Value error, Each text must contain at most 800 tokens",
        "line 8 (pair_id ' P8'): pair_id: Value error, pair_id must be non-empty, without "
        "surrounding whitespace, control characters or line separators",
        "line 9 (pair_id 'P1'): duplicate pair_id, first on line 1",
        # A duplicate of an invalid line is still found, so one rerun clears every problem.
        "line 10 (pair_id 'P5'): duplicate pair_id, first on line 5",
        "line 11: pair_id: Field required",
        "expected 12 pairs (--expected-pairs), found 10",
    )


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"", ("the file holds no pairs; expected one JSON object per line",)),
        (
            b"\n",
            (
                "line 1: blank; each line must hold one JSON object",
                "the file holds no pairs; expected one JSON object per line",
            ),
        ),
    ],
)
def test_empty_input_is_an_error(data: bytes, expected: tuple[str, ...]) -> None:
    assert problems_of(data, expected_pairs=60) == expected


def test_non_utf8_input_names_its_line() -> None:
    data = pair("P1").encode() + b"\n\xff\n"
    assert problems_of(data, expected_pairs=2) == ("line 2: invalid start byte",)


def test_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(SubmissionError) as caught:
        read_pairs(tmp_path / "absent.jsonl", expected_pairs=1)
    assert caught.value.summary == "Cannot read the pairs file"
    assert "No such file or directory" in caught.value.problems[0]


def test_reader_accepts_byte_order_mark_crlf_and_unicode_line_separator_in_text() -> None:
    # U+2028 is legal inside a JSON string; str.splitlines would cut the record in two.
    data = "\ufeff" + pair("P1", amendment="keep\u2028records") + "\r\n" + pair("P2") + "\r\n"
    pairs = parse_pairs(data.encode(), expected_pairs=2)
    assert [item.pair_id for item in pairs] == ["P1", "P2"]
    assert pairs[0].amendment.new == "keep\u2028records"
    assert pairs[0].amendment.old is None


@pytest.mark.parametrize(
    ("pair_id", "valid"),
    [
        ('P,1 "quoted"', True),
        ("Ä-4", True),
        ("pair 5", True),
        ("", False),
        ("P1 ", False),
        ("P\n1", False),
        ("P\u20281", False),
        ("P\x851", False),
        ("P\x001", False),
    ],
)
def test_pair_id_rejects_what_a_csv_reader_could_split_or_strip(pair_id: str, valid: bool) -> None:
    record = json.loads(pair(pair_id))
    if valid:
        assert SubmissionPair.model_validate(record).pair_id == pair_id
    else:
        with pytest.raises(ValidationError, match="pair_id must be non-empty"):
            SubmissionPair.model_validate(record)


def scored_pairs(*pair_ids: str) -> tuple[PairEvidence, ...]:
    data = "\n".join(pair(pair_id) for pair_id in pair_ids).encode()
    return score_pairs(parse_pairs(data, expected_pairs=len(pair_ids)))


@pytest.mark.parametrize(
    ("order", "scores", "expected"),
    [
        (
            (0, 1),
            {0: math.nan},
            ("pair_id 'A': influence_score nan is not a finite number in [0, 1]",),
        ),
        (
            (0, 1),
            {1: math.inf},
            ("pair_id 'B': influence_score inf is not a finite number in [0, 1]",),
        ),
        (
            (0, 1),
            {0: -0.01, 1: 1.01},
            (
                "pair_id 'A': influence_score -0.01 is not a finite number in [0, 1]",
                "pair_id 'B': influence_score 1.01 is not a finite number in [0, 1]",
            ),
        ),
        ((1, 0), {}, ("scored pair_ids differ from the input pair_ids or their order",)),
        (
            (0,),
            {},
            (
                "expected 2 scores, got 1",
                "scored pair_ids differ from the input pair_ids or their order",
            ),
        ),
        (
            (0, 0),
            {},
            (
                "scored pair_ids differ from the input pair_ids or their order",
                "scored pair_ids are not unique",
            ),
        ),
    ],
)
def test_score_check_rejects_anything_a_grader_could_misread(
    order: tuple[int, ...], scores: dict[int, float], expected: tuple[str, ...]
) -> None:
    """`order` picks scored pairs A (0) and B (1); `scores` overrides their scores."""
    valid = scored_pairs("A", "B")
    check_scores(["A", "B"], valid, expected_pairs=2)
    scored = [
        valid[index].model_copy(update={"influence_score": scores[index]})
        if index in scores
        else valid[index]
        for index in order
    ]
    with pytest.raises(SubmissionError) as caught:
        check_scores(["A", "B"], scored, expected_pairs=2)
    assert caught.value.problems == expected


@pytest.mark.parametrize(
    ("score", "text"), [(1e-05, "0.00001"), (1.0, "1.0"), (2 / 3, "0.6666666666666666")]
)
def test_score_format_is_shortest_round_trip_without_exponent(score: float, text: str) -> None:
    assert format_score(score) == text


def existing_outputs(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def test_failure_while_staging_leaves_previous_outputs_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / PAIRS_CSV).write_bytes(b"pair_id,influence_score\nOLD,0.5\n")
    (tmp_path / EVIDENCE_JSONL).write_bytes(b'{"old": true}\n')
    before = existing_outputs(tmp_path)
    calls: list[int] = []
    real_fsync = os.fsync

    def fail_on_second_file(descriptor: int) -> None:
        calls.append(descriptor)
        if len(calls) == 2:
            raise OSError(errno.ENOSPC, "No space left on device")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_on_second_file)
    with pytest.raises(OSError, match="No space left"):
        write_submission(tmp_path, scored_pairs("A", "B"))
    # The evidence copy staged before the failure is removed too.
    assert existing_outputs(tmp_path) == before
    assert len(calls) == 2


def test_failure_at_final_rename_keeps_pairs_csv_and_removes_staged_files(tmp_path: Path) -> None:
    """Only this rename failure separates the two files: new evidence, unchanged pairs.csv."""
    (tmp_path / PAIRS_CSV).mkdir()
    scored = scored_pairs("A")
    with pytest.raises((IsADirectoryError, PermissionError)):  # Windows raises PermissionError
        write_submission(tmp_path, scored)
    assert sorted(path.name for path in tmp_path.iterdir()) == [PAIRS_CSV, EVIDENCE_JSONL]
    assert (tmp_path / PAIRS_CSV).is_dir()
    assert (tmp_path / EVIDENCE_JSONL).read_text(encoding="utf-8").count("\n") == 1


WORDS = ("data", "shall", "not", "retain", "30", "days", "consent", "may", ",", ".", "Ä")
NEW_TEXTS = st.lists(st.sampled_from(WORDS), min_size=1, max_size=12).map(" ".join)
OLD_TEXTS = st.none() | st.lists(st.sampled_from(WORDS), max_size=12).map(" ".join)
TEXTS = st.fixed_dictionaries({"old": OLD_TEXTS, "new": NEW_TEXTS})
PAIR_IDS = st.text(
    st.characters(codec="utf-8", exclude_categories=("Cc", "Cs", "Zl", "Zp")),
    min_size=1,
    max_size=10,
).filter(lambda value: value == value.strip())


@st.composite
def pair_files(draw: st.DrawFn) -> list[dict[str, object]]:
    ids = draw(st.lists(PAIR_IDS, min_size=1, max_size=6, unique=True))
    return [{"pair_id": key, "amendment": draw(TEXTS), "submission": draw(TEXTS)} for key in ids]


def read_csv(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode(), newline="")))


@PROPERTY
@given(pair_files())
def test_outputs_keep_input_ids_in_order_with_bounded_scores(
    records: list[dict[str, object]],
) -> None:
    data = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records).encode()
    pairs = parse_pairs(data, expected_pairs=len(records))
    scored = score_pairs(pairs)
    check_scores([item.pair_id for item in pairs], scored, expected_pairs=len(records))
    header, *rows = read_csv(render_pairs_csv(scored))
    assert header == ["pair_id", "influence_score"]
    assert [row[0] for row in rows] == [record["pair_id"] for record in records]
    for row, item in zip(rows, scored, strict=True):
        score = float(row[1])
        assert math.isfinite(score)
        assert 0.0 <= score <= 1.0
        # Part 4 passes the comparison score through until a trained combiner exists.
        assert score == item.influence_score == item.comparison.score


FIXED_COMPARISON = ComparisonResult(
    mode="passages",
    method="lexical-passage-v1",
    score=0.0,
    evidence=(),
    negation_conflict=False,
    limitations=(),
)


@PROPERTY
@given(
    st.lists(
        st.tuples(PAIR_IDS, st.floats(min_value=0.0, max_value=1.0)),
        min_size=1,
        max_size=20,
        unique_by=lambda row: row[0],
    )
)
def test_csv_round_trips_ids_and_exact_scores(rows: list[tuple[str, float]]) -> None:
    scored = [
        PairEvidence(pair_id=pair_id, influence_score=score, comparison=FIXED_COMPARISON)
        for pair_id, score in rows
    ]
    _, *parsed = read_csv(render_pairs_csv(scored))
    assert [(pair_id, float(score)) for pair_id, score in parsed] == rows
    assert not any("e" in score for _, score in parsed)
