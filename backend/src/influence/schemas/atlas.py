"""Shared Influence Atlas contracts: the records every part reads and writes.

One file, one schema version. Parts 1 and 2 (collect, resolve actors) write law, document,
passage, amendment, article and actor records; parts 3 to 5 (find, verify, trace) write
asks, candidates, link assessments and outcomes; parts 6 to 8 read a graph snapshot. A
change here is a change for all three teams, so it goes through the integration owner.

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
LinkId = Annotated[str, StringConstraints(pattern=r"^link:\S+$")]
OutcomeId = Annotated[str, StringConstraints(pattern=r"^outcome:\S+$")]
ForecastId = Annotated[str, StringConstraints(pattern=r"^forecast:\S+$")]

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
    """A short stretch of a submission, the unit part 3 searches and part 4 quotes.

    Part 1 writes passages; ask extraction (part 3) reads them and writes `Ask` records.
    """

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


# --- Parts 3 and 4: asks, candidates, links ---------------------------------------------

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
    """A pair part 3 thinks worth checking. A candidate is not a link."""

    candidate_id: CandidateId
    procedure_id: ProcedureId
    amendment_id: AmendmentId
    ask_id: AskId
    lexical_rank: int | None = Field(default=None, ge=1)
    dense_rank: int | None = Field(default=None, ge=1)
    retrieval_score: float = Field(ge=0, allow_inf_nan=False)
    method: NonEmpty


type LinkStatus = Literal["published", "unconfirmed", "contradicted", "insufficient_evidence"]
type LinkTier = Literal["copied", "reworded", "same_direction"]
# `unknown_date` can never be published: an undated source is ineligible, not passing.
type TimeEligibility = Literal["ask_first", "amendment_first", "unknown_date"]


class LinkAssessment(AtlasRecord):
    """Part 4's verdict on one candidate, with the signals and quotations behind it.

    `support_score` is a support score, not a probability: no calibration exists yet.
    """

    link_id: LinkId
    procedure_id: ProcedureId
    candidate_id: CandidateId | None = None
    amendment_id: AmendmentId
    ask_id: AskId
    status: LinkStatus
    tier: LinkTier | None = None
    support_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    signals: dict[str, float] = Field(default_factory=dict)
    amendment_spans: tuple[SourceSpan, ...] = ()
    ask_spans: tuple[SourceSpan, ...] = ()
    time_eligibility: TimeEligibility
    method: NonEmpty
    method_revision: NonEmpty
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def published_links_are_defensible(self) -> Self:
        if self.status != "published":
            return self
        if self.time_eligibility != "ask_first":
            raise ValueError("A published link needs an ask dated before its amendment")
        if not self.amendment_spans or not self.ask_spans:
            raise ValueError("A published link quotes both the amendment and the ask")
        if self.tier is None:
            raise ValueError("A published link states its evidence tier")
        return self


# --- Part 5: outcomes -------------------------------------------------------------------

type OutcomeStage = Literal["heard", "parliament_position", "final_act"]
type OutcomeResult = Literal["full", "partial", "not_observed", "unknown"]
type OutcomeKind = Literal["wording", "reworded", "deletion", "status_quo"]
type OutcomeRelation = Literal["via_amendment", "direct_to_final"]


class Outcome(AtlasRecord):
    """What became of one ask at one stage. Unknown is a result and must say why."""

    outcome_id: OutcomeId
    procedure_id: ProcedureId
    ask_id: AskId
    link_id: LinkId | None = None
    amendment_id: AmendmentId | None = None
    relation: OutcomeRelation
    stage: OutcomeStage
    result: OutcomeResult
    kind: OutcomeKind | None = None
    article_id: ArticleId | None = None
    spans: tuple[SourceSpan, ...] = ()
    reason: str | None = None
    method: NonEmpty

    @model_validator(mode="after")
    def result_is_supported(self) -> Self:
        if self.result == "unknown" and not self.reason:
            raise ValueError("An unknown outcome must say why it could not be assessed")
        if self.result in ("full", "partial") and not self.spans:
            raise ValueError("An observed outcome quotes the text it was observed in")
        if self.relation == "via_amendment" and self.amendment_id is None:
            raise ValueError("An outcome via an amendment names that amendment")
        return self


# --- Part 7: forecasts ------------------------------------------------------------------

type ForecastScoreType = Literal["probability", "scenario", "rule"]


class Forecast(AtlasRecord):
    """A forecast or scenario for one open ask, built only from pre-cutoff information."""

    forecast_id: ForecastId
    procedure_id: ProcedureId
    ask_id: AskId
    as_of: AwareDatetime
    event: NonEmpty
    horizon: str | None = None
    score_type: ForecastScoreType
    # None for a scenario: without calibration evidence no number is published.
    score: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    scenario: str | None = None
    reasons: tuple[str, ...]
    missing_features: tuple[str, ...] = ()
    model_revision: NonEmpty

    @model_validator(mode="after")
    def score_matches_type(self) -> Self:
        if self.score_type == "probability" and self.score is None:
            raise ValueError("A probability forecast carries its score")
        if self.score_type == "scenario" and not self.scenario:
            raise ValueError("A scenario forecast describes the scenario")
        return self


# --- Part 6: graph ----------------------------------------------------------------------

type NodeKind = Literal["actor", "ask", "amendment", "article", "procedure", "topic"]
type Relation = Literal[
    "REQUESTED",
    "ECHOED_BY",
    "TABLED_BY",
    "EDITS",
    "ALIGNED_TO",
    "REALIZED_IN",
    "MET_WITH",
    "MEMBER_OF",
    "ABOUT",
]
# Relations our pipeline infers; each must open exact source evidence.
INFERRED_RELATIONS: frozenset[str] = frozenset({"ECHOED_BY", "ALIGNED_TO", "REALIZED_IN"})


class GraphNode(FrozenModel):
    node_id: NonEmpty
    kind: NodeKind
    label: NonEmpty
    # The record this node shows: an actor, ask, amendment, article or procedure ID.
    record_id: NonEmpty


class GraphEdge(FrozenModel):
    edge_id: NonEmpty
    relation: Relation
    source: NonEmpty
    target: NonEmpty
    spans: tuple[SourceSpan, ...] = ()
    link_id: LinkId | None = None
    outcome_id: OutcomeId | None = None
    dated_on: date | None = None

    @model_validator(mode="after")
    def inferred_edges_show_evidence(self) -> Self:
        if self.relation in INFERRED_RELATIONS and not self.spans:
            raise ValueError(f"A {self.relation} edge must carry the spans that support it")
        return self


class GraphSnapshot(AtlasRecord):
    """The graph the explorer, rankings and report read: published links only."""

    snapshot_id: NonEmpty
    run_id: NonEmpty
    generated_at: AwareDatetime
    procedure_ids: tuple[ProcedureId, ...]
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    coverage: dict[str, tuple[LayerCoverage, ...]]

    @model_validator(mode="after")
    def edges_join_known_nodes(self) -> Self:
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("The snapshot repeats a node ID")
        for edge in self.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError(f"Edge {edge.edge_id} joins a node the snapshot lacks")
        return self


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
