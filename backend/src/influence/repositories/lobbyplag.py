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


class RawProposal(RawRecord):
    doc_uid: str
    page: str
    text: RawText


class RawCandidate(RawRecord):
    amendment: str
    proposal: str
    verified: bool


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

    @classmethod
    def load(cls, directory: Path) -> DemoRepository:
        amendments = _index(_read(directory, "amendments", RawAmendment), "amendments")
        proposals = _index(_read(directory, "proposals", RawProposal), "proposals")
        raw_candidates = _read(directory, "plags", RawCandidate)
        candidates: dict[str, RawCandidate] = {}
        for candidate in raw_candidates:
            previous = candidates.get(candidate.uid)
            if previous is not None and previous != candidate:
                raise DatasetInvalidError(f"Conflicting duplicate candidate {candidate.uid}")
            candidates[candidate.uid] = candidate
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
