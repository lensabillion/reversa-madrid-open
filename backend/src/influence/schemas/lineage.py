"""Contracts of the lineage pipeline: which wording of the final law came from where.

The Atlas pipeline goes from a submission to an amendment to the law. Lineage starts from the
law: it finds the phrases of the final act that were not in the Commission's proposal, finds
the amendments whose inserted text contains them, and then who tabled those amendments and
which organisations' documents say the same thing earlier. It is a separate pipeline with its
own view (`lineage-1`) and leaves the `atlas-1` records untouched, until it has passed the
gates in `docs/design/` and replaces the first.

Pieces and who produces what:

* adoption (`services/lineage.py`): `AdoptedPhrase`, `AmendmentAdoption`, `Credit`;
* origin (`services/origin.py`): `OriginMatch`;
* review (`practice/lineage_review.py`): reads a `LineageView`, never writes one;
* assembly (`services/lineage_pipeline.py`, `influence lineage`): `LineageView`.

A shared phrase is evidence of shared wording, not of who wrote it first or why.
"""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from influence.schemas.atlas import (
    ActorId,
    AmendmentId,
    DocumentId,
    LayerCoverage,
    NonEmpty,
    ProcedureId,
    SourceSpan,
)
from influence.schemas.scoring import FrozenModel

LINEAGE_SCHEMA_VERSION = "lineage-1"
# Phrases are found as runs of consecutive words; an 8-word window is the unit that is
# looked up, and a run must be at least this many words to count as adopted wording.
NGRAM_WORDS = 8
MIN_ADOPTED_RUN_WORDS = 12

PhraseId = Annotated[str, StringConstraints(pattern=r"^phrase:[0-9a-f]{16}$")]
type AmendmentStage = Literal["committee", "plenary"]
type HolderKind = Literal["mep", "group", "committee_text", "organisation"]


class AdoptedPhrase(FrozenModel):
    """A run of words that stands in the final act, is not in the proposal, and was tabled.

    `text` is the folded words (lower case, alphanumeric tokens) joined by single spaces, so
    it compares across documents; `final_spans` quote the original text where it stands.
    """

    phrase_id: PhraseId
    text: NonEmpty
    words: int = Field(ge=MIN_ADOPTED_RUN_WORDS)
    final_spans: tuple[SourceSpan, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def words_count_the_text(self) -> Self:
        if self.words != len(self.text.split()):
            raise ValueError("`words` must equal the number of words in `text`")
        return self


class AmendmentAdoption(FrozenModel):
    """One amendment whose inserted wording reached the final act."""

    amendment_id: AmendmentId
    stage: AmendmentStage
    committee: str | None = None
    author_ids: tuple[ActorId, ...] = ()
    author_names: tuple[str, ...] = ()
    tabled_on: date | None = None
    phrase_ids: tuple[PhraseId, ...] = Field(min_length=1)
    adopted_words: int = Field(ge=MIN_ADOPTED_RUN_WORDS)
    inserted_words: int = Field(ge=1)
    longest_run: int = Field(ge=MIN_ADOPTED_RUN_WORDS)

    @model_validator(mode="after")
    def adoption_fits_inside_the_insertion(self) -> Self:
        if self.adopted_words > self.inserted_words:
            raise ValueError("An amendment cannot have adopted more words than it inserted")
        if self.longest_run > self.adopted_words:
            raise ValueError("The longest run cannot exceed the adopted words")
        return self


class Credit(FrozenModel):
    """How much adopted wording one holder can be credited with.

    Each phrase is worth 1, split equally among the holders credited for it (co-signers of
    the amendments that carry it), so a joint compromise amendment does not count in full for
    every signer. `committee_text` is the Parliament's own committee text, which has no
    individual author.
    """

    holder_id: NonEmpty
    holder_kind: HolderKind
    name: NonEmpty
    phrases: float = Field(ge=0, allow_inf_nan=False)
    distinct_phrases: int = Field(ge=0)
    amendments: int = Field(ge=0)


class OriginMatch(FrozenModel):
    """A document that says the adopted wording too, with its date against the amendments'."""

    phrase_id: PhraseId
    document_id: DocumentId
    actor_id: ActorId | None = None
    organisation: str | None = None
    published_at: AwareDatetime | None = None
    span: SourceSpan
    words: int = Field(ge=MIN_ADOPTED_RUN_WORDS)
    amendment_ids: tuple[AmendmentId, ...] = Field(min_length=1)
    earliest_amendment_on: date | None = None
    # None when either date is unknown: an undated document cannot be an origin.
    precedes: bool | None = None
    # A run that is a citation of another act ("... of the European Parliament and of the
    # Council of 20 May 2021 ...") is shared wording but not a request.
    is_citation: bool = False


class LineageCounts(FrozenModel):
    amendments: int = Field(ge=0)
    amendments_adopting: int = Field(ge=0)
    adopted_phrases: int = Field(ge=0)
    documents_read: int = Field(ge=0)
    documents_with_origin: int = Field(ge=0)


class LineageView(FrozenModel):
    """Everything the explorer and the review need about one law's lineage."""

    schema_version: Literal["lineage-1"] = LINEAGE_SCHEMA_VERSION
    procedure_id: ProcedureId
    slug: NonEmpty
    title: NonEmpty
    run_id: NonEmpty
    generated_at: AwareDatetime
    method: NonEmpty
    method_revision: NonEmpty
    coverage: tuple[LayerCoverage, ...] = ()
    counts: LineageCounts
    adopted_phrases: tuple[AdoptedPhrase, ...] = ()
    adoptions: tuple[AmendmentAdoption, ...] = ()
    origins: tuple[OriginMatch, ...] = ()
    credits: tuple[Credit, ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def references_resolve(self) -> Self:
        known = {phrase.phrase_id for phrase in self.adopted_phrases}
        if len(known) != len(self.adopted_phrases):
            raise ValueError("Duplicate phrase identifiers")
        for adoption in self.adoptions:
            if not set(adoption.phrase_ids) <= known:
                raise ValueError(f"{adoption.amendment_id} names a phrase that is not listed")
        for origin in self.origins:
            if origin.phrase_id not in known:
                raise ValueError(f"{origin.document_id} names a phrase that is not listed")
        amendments = {adoption.amendment_id for adoption in self.adoptions}
        if any(not set(origin.amendment_ids) <= amendments for origin in self.origins):
            raise ValueError("An origin names an amendment that has no adoption")
        scores = [credit.phrases for credit in self.credits]
        if scores != sorted(scores, reverse=True):
            raise ValueError("Credits are listed from most to least")
        return self


__all__ = [
    "LINEAGE_SCHEMA_VERSION",
    "MIN_ADOPTED_RUN_WORDS",
    "NGRAM_WORDS",
    "AdoptedPhrase",
    "AmendmentAdoption",
    "Credit",
    "LineageCounts",
    "LineageView",
    "OriginMatch",
]
