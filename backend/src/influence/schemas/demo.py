"""Read-only demo contracts keep historical evidence distinct from computed scores."""

from pydantic import BaseModel, ConfigDict

from influence.schemas.scoring import ScoreResult


class DemoModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DatasetOverview(DemoModel):
    amendments: int
    proposals: int
    documents: int
    organizations: int
    candidate_links: int
    duplicate_candidate_rows: int
    verified_links: int
    source_url: str
    coverage_note: str


class AmendmentSummary(DemoModel):
    id: str
    committee: str
    number: int
    authors: tuple[str, ...]
    relations: tuple[str, ...]
    verified_links: int
    candidate_links: int


class AmendmentPage(DemoModel):
    items: tuple[AmendmentSummary, ...]
    total: int
    offset: int
    limit: int


class SourceText(DemoModel):
    language: str
    old: str
    new: str


class SourceMatch(DemoModel):
    candidate_id: str
    proposal_id: str
    organization_id: str
    organization: str
    document_id: str
    document: str
    page: str
    text: SourceText
    historically_verified: bool
    score: ScoreResult | None
    score_unavailable_reason: str | None


class AmendmentDetail(DemoModel):
    amendment: AmendmentSummary
    text: SourceText
    sources: tuple[SourceMatch, ...]
    total_sources: int
    coverage_note: str


class OrganizationSummary(DemoModel):
    id: str
    name: str
    proposals: int
    verified_links: int
    amendments_echoing: int


class OrganizationPage(DemoModel):
    items: tuple[OrganizationSummary, ...]
    coverage_note: str
