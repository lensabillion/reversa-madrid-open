"""Null original wording means unknown; an empty original means a known insertion."""

from typing import Literal, Self

from pydantic import Field, model_validator

from influence.schemas.scoring import FrozenModel, MatchEvidence, TextChange


class InputText(FrozenModel):
    old: str | None
    new: str

    @model_validator(mode="after")
    def bounded_text(self) -> Self:
        TextChange(old=self.old or "", new=self.new)
        return self


class ComparisonRequest(FrozenModel):
    amendment: InputText
    submission: InputText

    @model_validator(mode="after")
    def comparable_passages(self) -> Self:
        if (self.amendment.old is None or self.submission.old is None) and (
            not self.amendment.new.strip() or not self.submission.new.strip()
        ):
            raise ValueError(
                "When an original is unknown, both proposed texts must contain text. "
                "Supply both originals to compare a deletion."
            )
        return self


class ComparisonResult(FrozenModel):
    mode: Literal["edits", "passages"]
    method: Literal["lexical-delta-v1", "lexical-passage-v1"]
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    evidence: tuple[MatchEvidence, ...]
    negation_conflict: bool
    limitations: tuple[str, ...]
