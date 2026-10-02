"""Run the frozen synthetic triplets through the lexical comparison baseline."""

import hashlib
import json
import math
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from influence.schemas.comparison import ComparisonRequest, InputText
from influence.services.comparison import compare_texts

FIXTURE = Path(__file__).resolve().parents[1] / "evaluation" / "diagnostics.json"


class DiagnosticCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    amendment: InputText
    preferred: InputText
    decoy: InputText


class DiagnosticFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal["synthetic-diagnostics-v1"]
    provenance: str = Field(min_length=1)
    cases: tuple[DiagnosticCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        ids = [case.id for case in self.cases]
        if any(not case_id.strip() for case_id in ids) or len(ids) != len(set(ids)):
            raise ValueError("Diagnostic case IDs must be nonempty and unique")
        return self


def evaluate(path: Path = FIXTURE) -> dict[str, object]:
    """Report synthetic preferred ordering; this does not measure historical influence."""
    contents = path.read_bytes()
    fixture = DiagnosticFixture.model_validate_json(contents)
    rows: list[dict[str, str | float]] = []
    preferred_above_decoy = ties = decoy_above_preferred = 0
    for case in fixture.cases:
        preferred = compare_texts(
            ComparisonRequest(amendment=case.amendment, submission=case.preferred)
        ).score
        decoy = compare_texts(
            ComparisonRequest(amendment=case.amendment, submission=case.decoy)
        ).score
        if not math.isfinite(preferred) or not math.isfinite(decoy):
            raise ValueError(f"Nonfinite score in diagnostic case {case.id}")
        if preferred > decoy:
            ordering = "preferred"
            preferred_above_decoy += 1
        elif preferred < decoy:
            ordering = "decoy"
            decoy_above_preferred += 1
        else:
            ordering = "tie"
            ties += 1
        rows.append(
            {
                "id": case.id,
                "category": case.category,
                "preferred_score": preferred,
                "decoy_score": decoy,
                "ordering": ordering,
            }
        )
    return {
        "kind": "synthetic-semantic-agreement-diagnostic",
        "scorer": "lexical",
        "fixture_version": fixture.version,
        "fixture_sha256": hashlib.sha256(contents).hexdigest(),
        "scope_note": (
            "Synthetic semantic agreement only; not influence accuracy or top-20 precision."
        ),
        "cases": rows,
        "aggregate": {
            "total": len(rows),
            "preferred_above_decoy": preferred_above_decoy,
            "ties": ties,
            "decoy_above_preferred": decoy_above_preferred,
        },
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2, sort_keys=True))
