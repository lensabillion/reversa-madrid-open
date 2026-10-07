"""Bounds on the token diffs used by lineage candidate queries."""

import pytest
from pydantic import ValidationError

from influence.schemas.scoring import TextChange


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


def test_changed_spans_keep_exact_unicode_offsets_and_skip_case_only_edits() -> None:
    from influence.services.scoring import changed_spans

    old = "Résumé: providers may keep logs."
    new = "Résumé: providers shall keep technical logs."
    spans = changed_spans(TextChange(old=old, new=new))
    assert [(span.operation, span.text) for span in spans] == [
        ("delete", "may"),
        ("insert", "shall"),
        ("insert", "technical"),
    ]
    for span in spans:
        source = old if span.operation == "delete" else new
        assert source[span.start : span.end] == span.text
    assert changed_spans(TextChange(old="KEEP logs", new="keep logs")) == ()
