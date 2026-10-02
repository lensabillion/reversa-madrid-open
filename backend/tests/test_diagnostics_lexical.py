"""The frozen synthetic diagnostic exposes lexical failure modes, not influence accuracy."""

import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import diagnostics_lexical
import pytest
from pydantic import ValidationError

from influence.schemas.comparison import ComparisonRequest


def test_frozen_lexical_diagnostic_reports_ordering_and_scope() -> None:
    report = diagnostics_lexical.evaluate()
    assert report["aggregate"] == {
        "total": 10,
        "preferred_above_decoy": 2,
        "ties": 0,
        "decoy_above_preferred": 8,
    }
    assert report["kind"] == "synthetic-semantic-agreement-diagnostic"
    assert "not influence accuracy or top-20 precision" in str(report["scope_note"])
    rows = cast(list[dict[str, str | float]], report["cases"])
    assert [row["id"] for row in rows] == [
        "paraphrase",
        "antonym",
        "quantity",
        "percentage",
        "boilerplate",
        "shared-deletion",
        "negation-scope",
        "legal-modality",
        "identical",
        "unchanged-law",
    ]
    assert rows[1]["ordering"] == "decoy"
    assert rows[8]["preferred_score"] == 1.0
    assert cast(float, rows[8]["decoy_score"]) < 1.0


@pytest.mark.parametrize(
    ("case_id", "message"), [("", "at least 1 character"), ("paraphrase", "nonempty and unique")]
)
def test_case_ids_must_be_nonempty_and_unique(tmp_path: Path, case_id: str, message: str) -> None:
    fixture = json.loads(diagnostics_lexical.FIXTURE.read_text(encoding="utf-8"))
    fixture["cases"][1]["id"] = case_id
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValidationError, match=message):
        diagnostics_lexical.evaluate(path)


def test_nonfinite_score_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def nonfinite(_request: ComparisonRequest) -> SimpleNamespace:
        return SimpleNamespace(score=math.nan)

    monkeypatch.setattr(diagnostics_lexical, "compare_texts", nonfinite)
    with pytest.raises(ValueError, match="Nonfinite score in diagnostic case paraphrase"):
        diagnostics_lexical.evaluate()
