"""Contracts for the candidate shortlist: bounded passages, never influence claims."""

from typing import Literal

from pydantic import Field

from influence.schemas.scoring import FrozenModel

type QueryKind = Literal["delta", "whole_text"]


class SourcePassage(FrozenModel):
    """A bounded slice of one source document.

    `start` and `end` are half-open Unicode code-point offsets into the unmodified
    document text, so `text == document[start:end]` and a later span can be checked.
    """

    document_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str


class PassageCandidate(FrozenModel):
    """One shortlisted passage with the neighbouring text a reader needs to judge it."""

    passage: SourcePassage
    context_start: int = Field(ge=0)
    context_end: int = Field(ge=0)
    rank: int = Field(ge=1)
    score: float = Field(gt=0, allow_inf_nan=False)
    matched_terms: tuple[str, ...]


class Shortlist(FrozenModel):
    """Ranked alternatives for one amendment; a candidate is not a link."""

    amendment_id: str = Field(min_length=1)
    # "delta": the query is the inserted and deleted words only, so wording shared with the
    # original law cannot match. "whole_text": the original is unknown, so the whole proposed
    # text is searched and shared law wording may inflate scores.
    query_kind: QueryKind
    query_terms: tuple[str, ...]
    candidates: tuple[PassageCandidate, ...]
    score_type: Literal["bm25"] = "bm25"
    method: Literal["bm25-passages-v1"] = "bm25-passages-v1"
    limitations: tuple[str, ...]


type ChangeKind = Literal["replace", "delete", "insert", "statement"]


class PassageChange(FrozenModel):
    """The change one submission passage asks for, with the exact words that say so.

    `start` and `end` are half-open code-point offsets into the passage given to the reader,
    so `text == passage[start:end]`. `old` is None when the passage does not say what the
    original wording is (kind "statement"); that is different from "" (kind "insert"),
    where the original is known to be empty.
    """

    kind: ChangeKind
    old: str | None
    new: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str
