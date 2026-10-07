"""Shared collection and lineage candidate contracts.

Collection writes law, document, passage, amendment, article and actor records. Lineage
reads those records, and its optional Jev path uses asks and BM25 candidates. The existing
atlas-1 serialization remains stable so collected bundles do not need rebuilding.

Three rules hold for every record:

- Unknown is never zero. A missing date, original wording or outcome is `None` (or the
  literal `"unknown"`), and a consumer must not treat it as a value.
- Evidence is exact. A `SourceSpan` holds half-open Unicode code-point offsets into the
  unmodified text it names, and the quoted text itself; the two are checked against each
  other when the span is built, and against the source by `span_matches`.
- Identifiers are canonical strings with a prefix that names the record type, built by
  the functions below and never by hand, so a join never depends on formatting.
"""

import re
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from influence.schemas.scoring import FrozenModel

# Bump on any change a consumer could notice; fixtures and manifests record it.
ATLAS_SCHEMA_VERSION = "atlas-1"
type SchemaVersion = Literal["atlas-1"]

# A procedure reference as the Legislative Observatory writes it: 2021/0106(COD).
SLUG_PATTERN = r"^\d{4}-\d{4}[A-Z]?-[A-Z]{3}$"
Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]

PROCEDURE_PATTERN = r"^\d{4}/\d{4}[A-Z]?\([A-Z]{3}\)$"
ProcedureId = Annotated[str, StringConstraints(pattern=PROCEDURE_PATTERN)]
# The Transparency Register's identificationCode: 880143435725-46.
RegisterId = Annotated[str, StringConstraints(pattern=r"^\d{6,}-\d{2}$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
NonEmpty = Annotated[str, StringConstraints(min_length=1)]

DocumentId = Annotated[str, StringConstraints(pattern=r"^doc:[a-z_]+:\S+$")]
ActorId = Annotated[str, StringConstraints(pattern=r"^actor:(tr|mep|name|citizens):\S+$")]
PassageId = Annotated[str, StringConstraints(pattern=r"^passage:\S+$")]
AskId = Annotated[str, StringConstraints(pattern=r"^ask:\S+$")]
AmendmentId = Annotated[str, StringConstraints(pattern=r"^am:\S+$")]
ArticleId = Annotated[str, StringConstraints(pattern=r"^art:\S+$")]
CandidateId = Annotated[str, StringConstraints(pattern=r"^cand:\S+$")]

_UNSAFE_ID_CHARACTERS = re.compile(r"[^A-Za-z0-9._-]+")


def id_part(value: str) -> str:
    """Reduce a source identifier to the characters every ID, path and URL accepts."""
    part = _UNSAFE_ID_CHARACTERS.sub("-", value).strip("-")
    if not part:
        raise ValueError(f"No usable identifier characters in {value!r}")
    return part


def document_id(source_kind: str, source_key: str) -> str:
    """`doc:<kind>:<key>`, where the key is the source's own identifier for the document."""
    return f"doc:{source_kind}:{id_part(source_key)}"


def register_actor_id(register_id: str) -> str:
    return f"actor:tr:{register_id}"


def mep_actor_id(mep_id: int) -> str:
    return f"actor:mep:{mep_id}"


def named_actor_id(source_kind: str, normalised_name: str) -> str:
    """An actor known only by a name in one source; never merged with a register entry."""
    return f"actor:name:{id_part(source_kind)}.{id_part(normalised_name)}"


# Private individuals are counted, never named (AGENTS.md, "Data and Challenge Rules").
CITIZENS_ACTOR_ID = "actor:citizens:aggregate"


class AtlasRecord(FrozenModel):
    schema_version: SchemaVersion = ATLAS_SCHEMA_VERSION


# --- Evidence ---------------------------------------------------------------------------

type SpanField = Literal["text", "old_text", "new_text", "justification"]


class SourceSpan(FrozenModel):
    """A quotation and where it sits: `record_id`'s `field`, code points `[start, end)`.

    `record_id` is the document, passage, amendment or article whose text the offsets
    index. Offsets count Unicode code points (Python `str` indices), not UTF-16 units:
    the frontend slices with `Array.from`.
    """

    record_id: NonEmpty
    field: SpanField = "text"
    page: int | None = Field(default=None, ge=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: NonEmpty

    @model_validator(mode="after")
    def offsets_describe_text(self) -> Self:
        if self.end - self.start != len(self.text):
            raise ValueError(
                f"Span [{self.start}, {self.end}) is {self.end - self.start} code points, "
                f"but its text has {len(self.text)}"
            )
        return self


def span_matches(span: SourceSpan, source_text: str) -> bool:
    """True when the source really holds the quoted text at the span's offsets."""
    return source_text[span.start : span.end] == span.text


# --- Coverage ---------------------------------------------------------------------------

type Layer = Literal[
    "metadata",
    "proposal",
    "parliament_position",
    "final_act",
    "committee_amendments",
    "plenary_amendments",
    "asks",
    "actors",
    "meetings",
    "votes",
]
# `missing`: the source lacks it. `not_collected`: this run did not try. `stale`: the
# source stopped updating before the procedure ended. See docs/plan.md, section 6.
type LayerStatus = Literal[
    "complete", "partial", "missing", "stale", "not_applicable", "not_collected"
]


class LayerCoverage(FrozenModel):
    layer: Layer
    status: LayerStatus
    # None means not counted, which is different from a counted zero.
    count: int | None = Field(default=None, ge=0)
    reason: str | None = None
    source_updated_on: date | None = None

    @model_validator(mode="after")
    def gaps_carry_a_reason(self) -> Self:
        if self.status != "complete" and not self.reason:
            raise ValueError(f"Layer {self.layer} is {self.status} and must say why")
        return self


# --- Part 1: collect --------------------------------------------------------------------

type SourceKind = Literal[
    "parltrack",
    "cellar",
    "ep_api",
    "hys_feedback",
    "hys_attachment",
    "register",
    "meetings",
    "votes",
    "public_statement",
]
type ExtractionStatus = Literal["extracted", "partial", "failed", "not_applicable"]


class SourceDocument(AtlasRecord):
    """One retrieved public file: where it came from, when, and what its bytes hash to."""

    document_id: DocumentId
    procedure_id: ProcedureId | None
    source_kind: SourceKind
    url: NonEmpty
    title: str | None = None
    # When the source says it was published. None stays None: an undated document is
    # never eligible as the origin of an amendment.
    published_at: AwareDatetime | None
    retrieved_at: AwareDatetime
    sha256: Sha256
    media_type: str | None = None
    language: str | None = None
    extraction_status: ExtractionStatus
    extraction_method: str | None = None
    text_characters: int | None = Field(default=None, ge=0)
    reuse_terms: str | None = None


class DocumentText(AtlasRecord):
    """A document's extracted text, the string every span into that document indexes."""

    document_id: DocumentId
    text: str


type LawStatus = Literal["completed", "ongoing", "withdrawn", "unknown"]


class LawRecord(AtlasRecord):
    """A resolved law. Identifiers a source did not confirm stay None, never guessed."""

    procedure_id: ProcedureId
    title: NonEmpty
    status: LawStatus
    stage_reached: str | None = None
    celex_proposal: str | None = None
    celex_final: str | None = None
    com_reference: str | None = None
    subjects: tuple[str, ...] = ()
    lead_committee: str | None = None
    proposed_on: date | None = None
    completed_on: date | None = None
    coverage: tuple[LayerCoverage, ...]

    @model_validator(mode="after")
    def one_row_per_layer(self) -> Self:
        layers = [item.layer for item in self.coverage]
        if len(layers) != len(set(layers)):
            raise ValueError("Coverage lists a layer more than once")
        return self


class Passage(AtlasRecord):
    """An exact stretch of a consultation submission searched by optional Jev retrieval."""

    passage_id: PassageId
    procedure_id: ProcedureId
    document_id: DocumentId
    actor_id: ActorId
    span: SourceSpan
    submitted_at: AwareDatetime | None
    language: str | None = None


type AmendmentStage = Literal["committee", "plenary"]


def _nothing(value: tuple[object, ...]) -> bool:
    return not value


class Amendment(AtlasRecord):
    """One tabled amendment. `old_text` None is unknown; an empty string is an insertion."""

    amendment_id: AmendmentId
    procedure_id: ProcedureId
    document_id: DocumentId
    stage: AmendmentStage
    committee: str | None = None
    number: int | None = Field(default=None, ge=0)
    author_ids: tuple[ActorId, ...] = ()
    author_names: tuple[str, ...] = ()
    # Each author's political group on `tabled_on`, aligned with `author_ids`; None where
    # the group on that day is unknown. Empty when the amendment was not annotated (a
    # bundle written before this field). `Actor.political_group` is the latest group,
    # for display; a Member who changed group was in another one when tabling. Left out
    # of the JSON when empty, so records written without it keep their bytes and hashes.
    author_groups: tuple[str | None, ...] = Field(default=(), exclude_if=_nothing)
    tabled_on: date | None
    target_provision: str | None = None
    old_text: str | None
    new_text: str
    justification: str | None = None
    language: str | None = None

    @model_validator(mode="after")
    def holds_some_text(self) -> Self:
        if not (self.old_text or "").strip() and not self.new_text.strip():
            raise ValueError("An amendment needs original or proposed wording")
        if self.author_groups and len(self.author_groups) != len(self.author_ids):
            raise ValueError("author_groups must align with author_ids")
        return self


type ArticleStage = Literal["proposal", "parliament_position", "final_act"]
type ProvisionKind = Literal["recital", "article", "paragraph", "point", "annex", "other"]


class ArticleVersion(AtlasRecord):
    """One provision of one version of the law. Final acts renumber: join on text."""

    article_id: ArticleId
    procedure_id: ProcedureId
    document_id: DocumentId
    stage: ArticleStage
    provision: NonEmpty
    kind: ProvisionKind
    text: NonEmpty
    version_date: date | None = None


# --- Part 2: actors ---------------------------------------------------------------------

type ActorKind = Literal["organisation", "mep", "citizens", "unknown"]
# How the identity was established. `ambiguous` and `unresolved` are results, not errors.
type ResolutionMethod = Literal[
    "register_id", "mep_id", "normalised_exact", "acronym", "fuzzy", "ambiguous", "unresolved"
]


class ActorAlias(FrozenModel):
    name: NonEmpty
    source_kind: SourceKind
    document_id: DocumentId | None = None


class Actor(AtlasRecord):
    """One identity. Two register IDs are never merged; a name match only proposes."""

    actor_id: ActorId
    kind: ActorKind
    name: NonEmpty
    register_id: RegisterId | None = None
    mep_id: int | None = Field(default=None, ge=1)
    category: str | None = None
    country: str | None = None
    political_group: str | None = None
    declared_cost_eur: float | None = Field(default=None, ge=0)
    declared_cost_raw: str | None = None
    aliases: tuple[ActorAlias, ...] = ()
    resolution: ResolutionMethod
    resolution_score: float | None = Field(default=None, ge=0, le=1)
    # Register entries a name could belong to when the match is ambiguous or fuzzy.
    candidate_ids: tuple[ActorId, ...] = ()

    @model_validator(mode="after")
    def identity_matches_method(self) -> Self:
        if self.resolution == "register_id" and self.register_id is None:
            raise ValueError("An actor resolved by register ID must carry that ID")
        if self.resolution == "mep_id" and self.mep_id is None:
            raise ValueError("An actor resolved by MEP ID must carry that ID")
        if self.resolution == "ambiguous" and len(self.candidate_ids) < 2:
            raise ValueError("An ambiguous actor lists the candidates it could be")
        return self


# --- Optional Jev retrieval: requests and candidate pairs ------------------------------

type Direction = Literal[
    "stricter", "weaker", "delete", "delay", "exempt", "add", "keep", "other", "unknown"
]


class Ask(AtlasRecord):
    """One requested change by one actor on one provision, quoted from its source."""

    ask_id: AskId
    procedure_id: ProcedureId
    actor_id: ActorId
    # More than one actor only for a coalition ask: one ask, joint attribution.
    joint_actor_ids: tuple[ActorId, ...] = ()
    document_id: DocumentId
    passage_id: PassageId | None = None
    span: SourceSpan
    requested_change: str | None = None
    target_provision: str | None = None
    direction: Direction = "unknown"
    submitted_at: AwareDatetime | None
    language: str | None = None
    extraction_method: NonEmpty


class Candidate(AtlasRecord):
    """A request/amendment pair shortlisted for the optional Jev origin judgment."""

    candidate_id: CandidateId
    procedure_id: ProcedureId
    amendment_id: AmendmentId
    ask_id: AskId
    lexical_rank: int | None = Field(default=None, ge=1)
    dense_rank: int | None = Field(default=None, ge=1)
    retrieval_score: float = Field(ge=0, allow_inf_nan=False)
    method: NonEmpty


# An undated source remains visible but cannot count as an earlier origin.
type TimeEligibility = Literal["ask_first", "amendment_first", "unknown_date"]


# --- Run manifest -----------------------------------------------------------------------

type StageStatus = Literal["complete", "partial", "failed", "skipped", "reused"]
type RunStatus = Literal["running", "complete", "failed"]


class OutputFile(FrozenModel):
    path: NonEmpty
    sha256: Sha256
    records: int | None = Field(default=None, ge=0)


class StageReceipt(FrozenModel):
    """What one stage of one run did. A receipt is reused only when `input_hash` matches."""

    stage: NonEmpty
    status: StageStatus
    input_hash: Sha256
    seconds: float = Field(ge=0, allow_inf_nan=False)
    counts: dict[str, int] = Field(default_factory=dict)
    errors: tuple[str, ...] = ()
    outputs: tuple[OutputFile, ...] = ()


class RunManifest(AtlasRecord):
    """One run of the pipeline for one law. Complete only after every output validates."""

    run_id: NonEmpty
    query: NonEmpty
    procedure_id: ProcedureId | None
    status: RunStatus
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    code_revision: NonEmpty
    config: dict[str, str] = Field(default_factory=dict)
    hardware: str | None = None
    stages: tuple[StageReceipt, ...] = ()
    coverage: tuple[LayerCoverage, ...] = ()

    @model_validator(mode="after")
    def completion_is_consistent(self) -> Self:
        if self.status == "complete":
            if self.completed_at is None or self.procedure_id is None:
                raise ValueError("A complete run records its law and completion time")
            if any(stage.status == "failed" for stage in self.stages):
                raise ValueError("A run with a failed stage is not complete")
        return self
