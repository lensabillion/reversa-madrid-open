"""Compact provenance for quotations, without copying full collected documents."""

from typing import Literal, Self

from pydantic import AwareDatetime, model_validator

from influence.schemas.atlas import DocumentId, NonEmpty, Sha256, SourceKind
from influence.schemas.scoring import FrozenModel

type SourceRecordKind = Literal["document_text", "amendment", "article"]


class LineageDocument(FrozenModel):
    """Metadata copied from the collected source, never inferred from a record ID."""

    document_id: DocumentId
    url: NonEmpty
    title: str | None
    source_kind: SourceKind
    published_at: AwareDatetime | None
    retrieved_at: AwareDatetime
    sha256: Sha256


class LineageSourceRecord(FrozenModel):
    """A quoted extracted record and its source file; offsets index the record field."""

    record_id: NonEmpty
    document_id: DocumentId
    record_type: SourceRecordKind
    label: str | None
    unavailable_reason: NonEmpty | None = None

    @model_validator(mode="after")
    def document_text_keeps_document_identity(self) -> Self:
        if self.record_type == "document_text" and self.record_id != self.document_id:
            raise ValueError("A document-text record is keyed by its own document identifier")
        return self
