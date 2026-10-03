"""The explorer's view of one law: what `GET /api/v1/atlas/{slug}` returns.

It carries the shared `atlas-1` records the frontend adapter validates again (the bundle's
keys are the camelCase names of `AtlasBundle` in `frontend/lib/atlas.ts`), the graph
snapshot built from them, and outcome counts the backend has already ordered: the page
renders them and never ranks or scores anything itself.
"""

from typing import Annotated, Literal

from pydantic import AliasChoices, AwareDatetime, Field, StringConstraints

from influence.schemas.atlas import (
    Actor,
    Amendment,
    ArticleVersion,
    Ask,
    DocumentText,
    GraphSnapshot,
    LawRecord,
    LayerCoverage,
    LinkAssessment,
    NonEmpty,
    Outcome,
    Passage,
    ProcedureId,
    SourceDocument,
)
from influence.schemas.scoring import FrozenModel

VIEW_SCHEMA_VERSION = "atlas-view-1"
# `procedure_slug` of a procedure reference: 2021/0106(COD) is 2021-0106-COD.
SLUG_PATTERN = r"^\d{4}-\d{4}[A-Z]?-[A-Z]{3}$"
Slug = Annotated[str, StringConstraints(pattern=SLUG_PATTERN)]


class AtlasBundleView(FrozenModel):
    """Every record the shown links reach, and nothing they do not."""

    laws: tuple[LawRecord, ...]
    documents: tuple[SourceDocument, ...]
    document_texts: tuple[DocumentText, ...] = Field(
        validation_alias=AliasChoices("document_texts", "documentTexts"),
        serialization_alias="documentTexts",
    )
    passages: tuple[Passage, ...]
    actors: tuple[Actor, ...]
    asks: tuple[Ask, ...]
    amendments: tuple[Amendment, ...]
    articles: tuple[ArticleVersion, ...]
    links: tuple[LinkAssessment, ...]
    outcomes: tuple[Outcome, ...]


class RankingRow(FrozenModel):
    """Final-act outcome counts for one actor, in the order the backend chose."""

    actor_id: NonEmpty
    actor_name: NonEmpty
    observed_asks: int = Field(ge=0)
    assessed_asks: int = Field(ge=0)
    full: int = Field(ge=0)
    partial: int = Field(ge=0)
    not_observed: int = Field(ge=0)
    unknown: int = Field(ge=0)
    full_win_rate: float | None = Field(default=None, ge=0, le=1)
    evidence_record_ids: tuple[str, ...] = ()


class AtlasView(FrozenModel):
    schema_version: Literal["atlas-view-1"] = VIEW_SCHEMA_VERSION
    procedure_id: ProcedureId
    slug: Slug
    title: NonEmpty
    run_id: NonEmpty
    generated_at: AwareDatetime
    # How asks were made; "passage-v0" means every consultation passage is one ask.
    ask_method: NonEmpty
    coverage: tuple[LayerCoverage, ...]
    bundle: AtlasBundleView
    snapshot: GraphSnapshot
    rankings: tuple[RankingRow, ...]
    limitations: tuple[str, ...]


class AtlasLawSummary(FrozenModel):
    slug: Slug
    procedure_id: ProcedureId
    title: NonEmpty
    run_id: NonEmpty
    published_links: int = Field(ge=0)


class InvalidAtlasView(FrozenModel):
    """A law directory whose view cannot be read, listed so one broken law hides no other."""

    slug: NonEmpty
    reason: NonEmpty


class AtlasLawList(FrozenModel):
    laws: tuple[AtlasLawSummary, ...]
    invalid: tuple[InvalidAtlasView, ...] = ()
