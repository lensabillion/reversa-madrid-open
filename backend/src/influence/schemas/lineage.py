"""Contracts of the lineage pipeline: which wording of the final law came from where.

The Atlas pipeline goes from a submission to an amendment to the law. Lineage starts from the
law: it finds the phrases of the final act that were not in the Commission's proposal, finds
the amendments whose inserted text contains them, and then who tabled those amendments and
which organisations' documents say the same thing earlier. It is a separate pipeline with its
own view (`lineage-1`) and leaves the `atlas-1` records untouched, until it has passed the
gates in `docs/design/` and replaces the first.

Pieces and who produces what:

* adoption (`services/lineage.py`): verbatim `AdoptedPhrase`, `AmendmentAdoption`, `Credit`;
* semantic adoption (`services/lineage_semantic.py`): the same records with kind "semantic",
  for wording that was reworded, found with Qwen embeddings and judged by the meaning judge;
* origin (`services/origin.py`): `OriginMatch`, verbatim and semantic;
* review (`practice/lineage_review.py`): reads a `LineageView`, never writes one;
* assembly (`services/lineage_pipeline.py`, `influence lineage`): `LineageView`.

A verbatim match is a run of identical words and is cheap and nearly unambiguous. A semantic
match says two texts ask for the same thing in different words; it is found by embeddings and
confirmed by a judge, so it carries a similarity and is reported apart from verbatim matches.
Either is evidence of shared wording or meaning, not of who wrote it first or why.
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
type MatchKind = Literal["verbatim", "semantic"]
type HolderKind = Literal["mep", "group", "committee_text", "organisation"]


class AdoptedPhrase(FrozenModel):
    """Wording that stands in the final act, is not in the proposal, and was tabled.

    Verbatim: a run of at least `MIN_ADOPTED_RUN_WORDS` identical words. Semantic: a segment
    of the final act (a sentence or paragraph) that an amendment's inserted text says again in
    other words, with the embedding `similarity` and, once judged, the judge's probability.
    `text` is the folded words (lower case, alphanumeric tokens) joined by single spaces, so
    it compares across documents; `final_spans` quote the original text where it stands.
    """

    phrase_id: PhraseId
    kind: MatchKind = "verbatim"
    text: NonEmpty
    words: int = Field(ge=1)
    final_spans: tuple[SourceSpan, ...] = Field(min_length=1)
    similarity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    judge_probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def words_count_the_text(self) -> Self:
        if self.words != len(self.text.split()):
            raise ValueError("`words` must equal the number of words in `text`")
        if self.kind == "verbatim" and self.words < MIN_ADOPTED_RUN_WORDS:
            raise ValueError("A verbatim phrase has at least MIN_ADOPTED_RUN_WORDS words")
        if self.kind == "semantic" and self.similarity is None:
            raise ValueError("A semantic phrase carries its similarity")
        return self


class AmendmentAdoption(FrozenModel):
    """One amendment whose inserted wording reached the final act, verbatim or reworded.

    An amendment can have one adoption of each kind.
    """

    amendment_id: AmendmentId
    kind: MatchKind = "verbatim"
    stage: AmendmentStage
    committee: str | None = None
    author_ids: tuple[ActorId, ...] = ()
    author_names: tuple[str, ...] = ()
    tabled_on: date | None = None
    phrase_ids: tuple[PhraseId, ...] = Field(min_length=1)
    adopted_words: int = Field(ge=1)
    inserted_words: int = Field(ge=1)
    longest_run: int = Field(ge=1)

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
    basis: MatchKind = "verbatim"
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
    kind: MatchKind = "verbatim"
    similarity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    words: int = Field(ge=1)
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
        for basis in ("verbatim", "semantic"):
            scores = [credit.phrases for credit in self.credits if credit.basis == basis]
            if scores != sorted(scores, reverse=True):
                raise ValueError("Credits are listed from most to least within each basis")
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
