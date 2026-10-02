"""Independent scoring contracts: edits, direction, evidence, and bounded input."""

from itertools import product
from math import isfinite

import pytest
from pydantic import ValidationError

from influence.schemas.scoring import ScoreRequest, TextChange
from influence.services.scoring import score_pair


@pytest.mark.parametrize(
    ("amendment", "submission", "expected"),
    [
        (("shall", "may"), ("shall", "may"), 1.0),
        (("retain data", ""), ("retain data", ""), 1.0),
        (("", "retain data"), ("retain data", ""), 0.0),
        (("unchanged", "unchanged"), ("unchanged", "unchanged"), 0.0),
        (
            ("same law shall apply", "same law may apply"),
            ("same law shall apply", "same law must apply"),
            0.5,
        ),
        (("", "retain data"), ("", "not retain data"), 0.0),
        (("", "alpha beta"), ("", "alpha gamma"), 1 / 3),
    ],
)
def test_score_contract(
    amendment: tuple[str, str], submission: tuple[str, str], expected: float
) -> None:
    result = score_pair(
        ScoreRequest(
            amendment=TextChange(old=amendment[0], new=amendment[1]),
            submission=TextChange(old=submission[0], new=submission[1]),
        )
    )
    assert result.score == pytest.approx(expected)
    assert result.score_type == "lexical_similarity"
    assert result.method == "lexical-delta-v1"
    assert result.limitations


def test_original_unicode_offsets_and_separate_diff_runs() -> None:
    change = TextChange(old="😀 café base 古 old", new="😀 CAFÉ added base β 2.5%")
    result = score_pair(ScoreRequest(amendment=change, submission=change))
    assert result.score == 1.0
    assert [(span.operation, span.text) for span in result.amendment_changes] == [
        ("insert", "added"),
        ("delete", "古 old"),
        ("insert", "β 2.5%"),
    ]
    for span in result.amendment_changes:
        original = change.new if span.operation == "insert" else change.old
        assert original[span.start : span.end] == span.text
    for match in result.evidence:
        original = change.new if match.operation == "insert" else change.old
        assert original[match.amendment.start : match.amendment.end] == match.amendment.text
        assert original[match.submission.start : match.submission.end] == match.submission.text
        assert "base" not in match.amendment.text
        assert match.amendment.text != "added β"


def test_punctuation_numbers_and_case_are_explicit() -> None:
    first = TextChange(old="", new="Pay 2.5%, now!")
    second = TextChange(old="", new="PAY 25%, now?")
    result = score_pair(ScoreRequest(amendment=first, submission=second))
    assert 0 < result.score < 1
    assert all("2.5" not in item.amendment.text for item in result.evidence)


def test_symmetric_finite_deterministic_scores_on_edge_matrix() -> None:
    changes = [
        TextChange(old=old, new=new)
        for old, new in [
            ("a", ""),
            ("", "a"),
            ("a", "a"),
            ("a b", "b a"),
            ("", "a a a"),
            ("not a", "a"),
            ("", " "),
            ("x", "\n x  "),
        ]
        if old.strip() or new.strip()
    ]
    for amendment, submission in product(changes, repeat=2):
        request = ScoreRequest(amendment=amendment, submission=submission)
        forward = score_pair(request)
        reverse = score_pair(ScoreRequest(amendment=submission, submission=amendment))
        assert isfinite(forward.score)
        assert 0 <= forward.score <= 1
        assert forward.score == reverse.score
        assert forward == score_pair(request)


@pytest.mark.parametrize(
    "payload",
    [
        {"old": "", "new": "  \t"},
        {"old": "x" * 12001, "new": ""},
        {"old": "", "new": "a " * 801},
        {"old": "a", "new": "b", "unknown": "c"},
        {"old": 3, "new": "b"},
    ],
)
def test_rejects_invalid_or_excessive_input(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TextChange.model_validate(payload)


def test_accepts_exact_limits_and_freezes_validated_input() -> None:
    change = TextChange(old="x" * 12000, new="a " * 800)
    with pytest.raises(ValidationError, match="frozen"):
        change.old = "changed"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ScoreRequest.model_validate(
            {
                "amendment": change,
                "submission": change,
                "unknown": "c",
            }
        )
