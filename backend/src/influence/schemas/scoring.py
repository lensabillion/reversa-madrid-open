"""Bounded immutable contracts for an explainable lexical baseline."""

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Keep numbers (including decimal percentages), Unicode words, and punctuation.
TOKEN_PATTERN = re.compile(r"\d+(?:[.,]\d+)*(?:%)?|\w+|[^\w\s]")
MAX_TEXT_LENGTH = 12_000
MAX_TOKENS = 800
type Operation = Literal["insert", "delete"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TextChange(FrozenModel):
    old: str = Field(max_length=MAX_TEXT_LENGTH)
    new: str = Field(max_length=MAX_TEXT_LENGTH)

    @model_validator(mode="after")
    def bounded_change(self) -> Self:
        if not self.old.strip() and not self.new.strip():
            raise ValueError("At least one of old and new must contain non-whitespace text")
        if any(len(TOKEN_PATTERN.findall(text)) > MAX_TOKENS for text in (self.old, self.new)):
            raise ValueError(f"Each text must contain at most {MAX_TOKENS} tokens")
        return self


class ScoreRequest(FrozenModel):
    amendment: TextChange
    submission: TextChange


class TextSpan(FrozenModel):
    """Half-open Python Unicode code-point offsets into the unmodified source."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str


class ChangeSpan(TextSpan):
    """Insertions index `new`; deletions index `old`. Whitespace alone is ignored."""

    operation: Operation


class MatchEvidence(FrozenModel):
    operation: Operation
    amendment: TextSpan
    submission: TextSpan


class ScoreResult(FrozenModel):
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    score_type: Literal["lexical_similarity"] = "lexical_similarity"
    method: Literal["lexical-delta-v1"] = "lexical-delta-v1"
    amendment_changes: tuple[ChangeSpan, ...]
    submission_changes: tuple[ChangeSpan, ...]
    evidence: tuple[MatchEvidence, ...]
    negation_conflict: bool
    limitations: tuple[str, ...]
