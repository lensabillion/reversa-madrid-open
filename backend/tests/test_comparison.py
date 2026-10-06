"""Unknown originals must never be reported as known empty redlines."""

import pytest
from pydantic import ValidationError

from influence.schemas.comparison import ComparisonRequest, InputText
from influence.services.comparison import compare_texts


@pytest.mark.parametrize(
    ("left", "right", "mode", "score"),
    [
        (None, None, "passages", 1.0),
        ("same", None, "passages", 1.0),
        ("same", "same", "edits", 0.0),
        ("", "", "edits", 1.0),
    ],
)
def test_missing_originals_choose_a_different_comparison(
    left: str | None, right: str | None, mode: str, score: float
) -> None:
    request = ComparisonRequest(
        amendment=InputText(old=left, new="same"),
        submission=InputText(old=right, new="same"),
    )
    result = compare_texts(request)
    assert result.mode == mode
    assert result.score == score
    assert result.method == ("lexical-delta-v1" if mode == "edits" else "lexical-passage-v1")
    assert "probability" in " ".join(result.limitations)
    assert request.amendment.old == left
    assert "amendment_changes" not in result.model_dump()


def test_passage_evidence_preserves_original_offsets() -> None:
    request = ComparisonRequest(
        amendment=InputText(old=None, new="😀 keep records"),
        submission=InputText(old=None, new="keep records safely"),
    )
    result = compare_texts(request)
    assert 0 < result.score < 1
    assert result.evidence
    for evidence in result.evidence:
        assert (
            request.amendment.new[evidence.amendment.start : evidence.amendment.end]
            == evidence.amendment.text
        )
        assert (
            request.submission.new[evidence.submission.start : evidence.submission.end]
            == evidence.submission.text
        )


@pytest.mark.parametrize("text", ["", "x" * 12001, "word " * 801])
def test_input_contract_reuses_scorer_bounds(text: str) -> None:
    with pytest.raises(ValidationError):
        InputText(old=None, new=text)


@pytest.mark.parametrize("reverse", [False, True])
def test_deletion_with_unknown_other_original_is_validation_error(reverse: bool) -> None:
    texts = [{"old": "deleted", "new": ""}, {"old": None, "new": "deleted"}]
    if reverse:
        texts.reverse()
    with pytest.raises(ValidationError, match="Supply both originals"):
        ComparisonRequest.model_validate({"amendment": texts[0], "submission": texts[1]})


def test_known_deletions_still_compare() -> None:
    result = compare_texts(
        ComparisonRequest(
            amendment=InputText(old="deleted words", new=""),
            submission=InputText(old="deleted words", new=""),
        )
    )
    assert result.mode == "edits"
    assert result.score == 1.0
    assert all(item.operation == "delete" for item in result.evidence)
