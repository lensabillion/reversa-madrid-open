"""The parsed tables and their keys: the contract every parser writes and reader reads.

One row per record, provenance on every row, JSON Lines on disk. JSON Lines rather than
CSV because legal text contains every delimiter; rather than Parquet because Parquet
needs a new dependency (pyarrow) that the supply-chain policy has not cleared. The row
models are the contract, so changing the container later does not change any parser.
"""

from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from influence.extraction.files import write_bytes_atomic

TABLE_NAMES = frozenset({"actors", "meetings", "asks", "amendments", "articles", "links"})

type ActorCategory = Literal[
    "company", "trade_association", "ngo", "think_tank", "law_firm", "other", "unknown"
]
type Institution = Literal["commission", "parliament", "council"]
type AskChannel = Literal["hys_feedback", "hys_attachment", "position_paper"]
type AmendmentStatus = Literal["adopted", "partial", "not_found", "unknown"]
type ArticleVersion = Literal["proposal", "final"]
type ArticleKind = Literal["article", "paragraph", "point", "recital"]
type MatchMethod = Literal[
    "registration_id", "normalised_exact", "acronym", "fuzzy", "manual", "ambiguous", "unresolved"
]


class TableError(ValueError):
    """A table file could not be read or validated."""


class ExtractedRow(BaseModel):
    """Provenance travels with the data: the jury picks edges at random and asks to see it."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    source_url: str = Field(min_length=1)
    fetched_at: datetime
    extraction_method: str = Field(min_length=1)


class ActorRow(ExtractedRow):
    actor_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    acronym: str | None
    category: ActorCategory
    country: str | None
    # Declared lobbying cost. Bands in some years and exact values in others, so the
    # normalised midpoint and the raw declaration are both kept; spend is a weak signal.
    budget_eur: float | None
    budget_raw: str | None
    accredited_lobbyists: int | None = Field(default=None, ge=0)
    interests: tuple[str, ...] = ()


class MeetingRow(ExtractedRow):
    meeting_id: str = Field(min_length=1)
    date: datetime
    institution: Institution
    host: str
    actor_raw_name: str = Field(min_length=1)
    actor_id: str | None
    match_method: MatchMethod
    match_score: float | None = Field(default=None, ge=0.0, le=1.0)
    subject: str


class AskRow(ExtractedRow):
    """One text chunk from one submission, not one submission: a paper carries many asks."""

    ask_id: str = Field(min_length=1)
    law_id: str = Field(min_length=1)
    actor_raw_name: str = Field(min_length=1)
    actor_id: str | None
    match_method: MatchMethod
    submitted_at: datetime | None
    channel: AskChannel
    text: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    offset: int | None = Field(default=None, ge=0)


class AmendmentRow(ExtractedRow):
    """Keyed by document and number: amendment numbering restarts in every document."""

    amendment_id: str = Field(min_length=1)
    law_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    number: int = Field(ge=1)
    authors: tuple[str, ...]
    committee: str | None
    target_unit: str
    text_original: str
    text_proposed: str
    justification: str | None
    status: AmendmentStatus
    matched_unit_id: str | None
    # A compromise amendment merges several originals and often names no author.
    compromise: bool = False


class ArticleRow(ExtractedRow):
    law_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    version: ArticleVersion
    kind: ArticleKind
    text: str
    # None until the proposal-to-final diff runs; unchanged text cannot be evidence.
    changed_vs_proposal: bool | None


class LinkRow(ExtractedRow):
    ask_id: str = Field(min_length=1)
    amendment_id: str | None
    unit_id: str | None
    score: float = Field(ge=0.0, le=1.0)
    method: str = Field(min_length=1)
    boilerplate_flag: bool


def write_table(path: Path, rows: Iterable[ExtractedRow]) -> int:
    """Write JSON Lines atomically and return the row count."""
    lines = [row.model_dump_json() for row in rows]
    write_bytes_atomic(path, "".join(f"{line}\n" for line in lines).encode("utf-8"))
    return len(lines)


def read_table[T: ExtractedRow](path: Path, model: type[T]) -> Iterator[T]:
    """Validate every line, naming the line number of the first failure."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise TableError(f"Cannot read {path.name}") from error
    for number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            yield model.model_validate_json(line)
        except ValidationError as error:
            raise TableError(f"{path.name} line {number} is invalid: {error}") from error
