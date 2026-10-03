"""Load immutable LobbyPlag records, rejecting incomplete or inconsistent snapshots."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class DatasetUnavailableError(Exception):
    """A required local dataset file could not be read."""


class DatasetInvalidError(Exception):
    """A dataset failed schema or relational validation."""


class EntityNotFoundError(Exception):
    """The requested entity is absent from a valid dataset."""


class RawRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)
    uid: str = Field(min_length=1)


class RawText(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)
    old: str
    new: str
    lang: str = "en"


class RawAmendment(RawRecord):
    committee: str
    number: int
    authors: tuple[str, ...]
    relations: tuple[str, ...]
    text: tuple[RawText, ...] = Field(min_length=1)

    def text_in(self, language: str) -> RawText | None:
        return next((text for text in self.text if text.lang == language), None)


class RawProposal(RawRecord):
    doc_uid: str
    page: str
    text: RawText


class RawProcessing(BaseModel):
    """LobbyPlag's crowd-check tallies: how often volunteers checked, and voted yes."""

    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)
    checked: int = Field(ge=0)
    verified: int = Field(ge=0)


class RawCandidate(RawRecord):
    """A pair LobbyPlag's matcher proposed. `match` is that matcher's similarity score."""

    amendment: str
    proposal: str
    verified: bool
    match: float = Field(ge=0, le=1, allow_inf_nan=False)
    processing: RawProcessing


def _merge_rows(previous: RawCandidate, candidate: RawCandidate) -> RawCandidate:
    """Coalesce rows that repeat one candidate identifier.

    Upstream repeats a candidate once per related law location; two identifiers carry a crowd
    check on only one of their rows. A check of any row is a check of the same pair, so the
    tallies merge by maximum: idempotent for exact copies, and a yes vote anywhere survives.
    Any other disagreement is a conflict.
    """
    if previous.model_dump(exclude={"processing"}) != candidate.model_dump(exclude={"processing"}):
        raise DatasetInvalidError(f"Conflicting duplicate candidate {candidate.uid}")
    return previous.model_copy(
        update={
            "processing": RawProcessing(
                checked=max(previous.processing.checked, candidate.processing.checked),
                verified=max(previous.processing.verified, candidate.processing.verified),
            )
        }
    )


class RawDocument(RawRecord):
    filename: str
    lobbyist: str | None
    lang: str


class RawOrganization(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)
    id: str = Field(min_length=1)
    title: str


def _read[T: BaseModel](directory: Path, name: str, model: type[T]) -> tuple[T, ...]:
    try:
        content = (directory / f"{name}.json").read_bytes()
    except OSError as error:
        raise DatasetUnavailableError(f"Cannot read {name}.json") from error
    try:
        return TypeAdapter(tuple[model, ...]).validate_json(content)
    except ValidationError as error:
        raise DatasetInvalidError(f"Invalid {name}.json: {error}") from error


def _index[T: RawRecord](records: tuple[T, ...], name: str) -> Mapping[str, T]:
    index = {record.uid: record for record in records}
    if len(index) != len(records):
        raise DatasetInvalidError(f"Duplicate identifiers in {name}")
    return MappingProxyType(index)


@dataclass(frozen=True)
class DemoRepository:
    amendments: Mapping[str, RawAmendment]
    proposals: Mapping[str, RawProposal]
    candidates: Mapping[str, RawCandidate]
    documents: Mapping[str, RawDocument]
    organizations: Mapping[str, RawOrganization]
    duplicate_candidate_rows: int = 0
    # Candidate identifiers whose repeated rows disagreed on crowd tallies (merged by maximum).
    merged_crowd_tallies: int = 0

    @classmethod
    def load(cls, directory: Path) -> DemoRepository:
        amendments = _index(_read(directory, "amendments", RawAmendment), "amendments")
        proposals = _index(_read(directory, "proposals", RawProposal), "proposals")
        raw_candidates = _read(directory, "plags", RawCandidate)
        candidates: dict[str, RawCandidate] = {}
        merged_tallies: set[str] = set()
        for candidate in raw_candidates:
            previous = candidates.get(candidate.uid)
            if previous is None:
                candidates[candidate.uid] = candidate
                continue
            if previous.processing != candidate.processing:
                merged_tallies.add(candidate.uid)
            candidates[candidate.uid] = _merge_rows(previous, candidate)
        documents = _index(_read(directory, "documents", RawDocument), "documents")
        raw_organizations = _read(directory, "lobbyists", RawOrganization)
        organizations = {record.id: record for record in raw_organizations}
        if len(organizations) != len(raw_organizations):
            raise DatasetInvalidError("Duplicate identifiers in lobbyists")
        for document in documents.values():
            if document.lobbyist is not None and document.lobbyist not in organizations:
                raise DatasetInvalidError(f"Unknown organization for document {document.uid}")
        for proposal in proposals.values():
            if proposal.doc_uid not in documents:
                raise DatasetInvalidError(f"Unknown document for proposal {proposal.uid}")
            if documents[proposal.doc_uid].lobbyist is None:
                raise DatasetInvalidError(f"Unattributed proposal {proposal.uid}")
        candidate_pairs: set[tuple[str, str]] = set()
        for candidate in candidates.values():
            if candidate.amendment not in amendments or candidate.proposal not in proposals:
                raise DatasetInvalidError(f"Dangling candidate {candidate.uid}")
            pair = (candidate.amendment, candidate.proposal)
            if pair in candidate_pairs:
                raise DatasetInvalidError(f"Duplicate candidate pair {candidate.uid}")
            candidate_pairs.add(pair)
        return cls(
            amendments,
            proposals,
            MappingProxyType(candidates),
            documents,
            MappingProxyType(organizations),
            len(raw_candidates) - len(candidates),
            len(merged_tallies),
        )

    def amendment(self, amendment_id: str) -> RawAmendment:
        try:
            return self.amendments[amendment_id]
        except KeyError as error:
            raise EntityNotFoundError(f"Unknown amendment {amendment_id}") from error

    def organization_for(self, proposal: RawProposal) -> RawOrganization:
        organization_id = self.documents[proposal.doc_uid].lobbyist
        if organization_id is None:
            raise DatasetInvalidError(f"Unattributed proposal {proposal.uid}")
        return self.organizations[organization_id]
