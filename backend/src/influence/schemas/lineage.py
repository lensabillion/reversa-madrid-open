"""Contracts of lineage: which wording of the final law came from where.

Lineage starts from new wording in the final act, finds amendments that carry it, and
traces their wording to earlier consultation documents. Exact matches retain Unicode
source offsets and whole credit. The optional Jev path adds judged reworded origins on
BM25's bounded shortlist; unknown inputs and limits remain explicit in the view.
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
    TimeEligibility,
)
from influence.schemas.scoring import TOKEN_PATTERN, FrozenModel

LINEAGE_SCHEMA_VERSION = "lineage-2"
# Phrases are found as runs of consecutive words; an 8-word window is the unit that is
# looked up, and a run must be at least this many words to count as shared wording. A run
# must also hold rare words (`services/lineage.Rarity`), so the law's own formulas do not
# count. Provisional: chosen by the owner on 3 October, not calibrated.
NGRAM_WORDS = 8
MIN_ADOPTED_RUN_WORDS = 8
# A phrase carried by amendments of at least this many different political groups is
# coalition wording rather than one group's request.
COALITION_GROUPS = 2

PhraseId = Annotated[str, StringConstraints(pattern=r"^phrase:[0-9a-f]{16}$")]
type AmendmentStage = Literal["committee", "plenary"]
type MatchKind = Literal["verbatim", "semantic"]
type HolderKind = Literal["mep", "group", "unresolved", "committee_text", "organisation"]
type AdoptionStatus = Literal["computed", "unknown"]
_KIND_ORDER: dict[str, int] = {
    "mep": 0,
    "group": 1,
    "unresolved": 2,
    "committee_text": 3,
    "organisation": 4,
}
_ELIGIBILITY: dict[bool | None, str] = {
    True: "ask_first",
    False: "amendment_first",
    None: "unknown_date",
}


class AdoptedPhrase(FrozenModel):
    """Wording that stands in the final act, is not in the proposal, and was tabled.

    Verbatim: one interval of the final act of at least `MIN_ADOPTED_RUN_WORDS` words, the
    union of the runs amendments share with it, so overlapping runs merge and one stretch of
    the law is one phrase with one span. Semantic: a segment of the final act that an
    amendment's text says again in other words, with the embedding `similarity`.
    `text` is the folded words (lower case, alphanumeric tokens) joined by single spaces, so
    it compares across documents; `final_spans` quote the original text where it stands.
    `holders` are the credit keys of everyone credited with it (see `Credit`); the phrase is
    joint when there is more than one.
    """

    phrase_id: PhraseId
    kind: MatchKind = "verbatim"
    text: NonEmpty
    words: int = Field(ge=1)
    final_spans: tuple[SourceSpan, ...] = Field(min_length=1)
    similarity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    judge_probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    holders: tuple[NonEmpty, ...] = ()

    @property
    def joint(self) -> bool:
        return len(self.holders) > 1

    @model_validator(mode="after")
    def words_count_the_text(self) -> Self:
        if self.words != len(self.text.split()):
            raise ValueError("`words` must equal the number of words in `text`")
        if self.kind == "verbatim" and self.words < MIN_ADOPTED_RUN_WORDS:
            raise ValueError("A verbatim phrase has at least MIN_ADOPTED_RUN_WORDS words")
        if self.kind == "semantic" and self.similarity is None:
            raise ValueError("A semantic phrase carries its similarity")
        return self


class TabledPhrase(FrozenModel):
    """Wording that amendments insert and a document also says, whether or not it was adopted.

    It lets an `OriginMatch` tie a document to an amendment that did not reach the final act.
    Adopted wording is an `AdoptedPhrase`; a phrase is one or the other, never both.
    """

    phrase_id: PhraseId
    text: NonEmpty
    words: int = Field(ge=1)
    amendment_ids: tuple[AmendmentId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def words_count_the_text(self) -> Self:
        if self.words != len(self.text.split()):
            raise ValueError("`words` must equal the number of words in `text`")
        return self


def _folded_words(text: str) -> tuple[str, ...]:
    return tuple(
        token.group().casefold()
        for token in TOKEN_PATTERN.finditer(text)
        if any(character.isalnum() for character in token.group())
    )


def _span_word_interval(parent: SourceSpan, child: SourceSpan) -> tuple[int, int]:
    """Validate a quote's exact parent occurrence and recover its word interval."""
    if (
        parent.record_id != child.record_id
        or parent.field != child.field
        or not parent.start <= child.start < child.end <= parent.end
        or parent.text[child.start - parent.start : child.end - parent.start] != child.text
    ):
        raise ValueError("An evidence projection must quote its exact parent occurrence")
    words = tuple(
        token
        for token in TOKEN_PATTERN.finditer(parent.text)
        if any(character.isalnum() for character in token.group())
    )
    starts = {parent.start + token.start(): index for index, token in enumerate(words)}
    ends = {parent.start + token.end(): index + 1 for index, token in enumerate(words)}
    first, end = starts.get(child.start), ends.get(child.end)
    if first is None or end is None:
        raise ValueError("Evidence projections must align with word boundaries")
    return first, end


class AdoptionEvidence(FrozenModel):
    """One accepted amendment run at one exact occurrence in the final act.

    Offsets in `inserted_word_offsets` index the folded words of this run, never the
    merged phrase or the full amendment. The producer checks rarity and raw source slices.
    """

    evidence_id: NonEmpty
    phrase_id: PhraseId
    amendment_span: SourceSpan
    final_span: SourceSpan
    inserted_word_offsets: tuple[int, ...]

    @model_validator(mode="after")
    def run_and_insertions_agree(self) -> Self:
        amendment = _folded_words(self.amendment_span.text)
        final = _folded_words(self.final_span.text)
        if self.amendment_span.field != "new_text" or self.final_span.field != "text":
            raise ValueError("Adoption evidence quotes amendment new_text and final text")
        if amendment != final or len(amendment) < MIN_ADOPTED_RUN_WORDS:
            raise ValueError("Adoption evidence shares at least eight consecutive folded words")
        offsets = self.inserted_word_offsets
        if (
            not offsets
            or offsets != tuple(sorted(set(offsets)))
            or offsets[0] < 0
            or offsets[-1] >= len(amendment)
        ):
            raise ValueError(
                "Inserted word offsets are nonempty, sorted, unique and within the run"
            )
        return self


class OriginSupport(FrozenModel):
    """One exact consultation/amendment/final projection of accepted carrier evidence."""

    support_id: NonEmpty
    adoption_evidence_id: NonEmpty
    amendment_id: AmendmentId
    submission_span: SourceSpan
    amendment_span: SourceSpan
    final_span: SourceSpan

    @model_validator(mode="after")
    def projections_share_the_same_words(self) -> Self:
        submission = _folded_words(self.submission_span.text)
        if (
            self.submission_span.field != "text"
            or self.amendment_span.field != "new_text"
            or self.final_span.field != "text"
        ):
            raise ValueError(
                "Origin support quotes submission text, amendment new_text and final text"
            )
        if (
            len(submission) < MIN_ADOPTED_RUN_WORDS
            or submission != _folded_words(self.amendment_span.text)
            or submission != _folded_words(self.final_span.text)
        ):
            raise ValueError("Origin support shares at least eight consecutive folded words")
        return self


class AmendmentAdoption(FrozenModel):
    """One amendment whose new wording reached the final act, verbatim or reworded.

    An amendment can have one adoption of each kind. A run counts when it holds at least one
    word the amendment inserted, so `adopted_words` (the amendment's words inside adopted
    runs) can exceed `inserted_words` when an insertion rewrites part of a sentence; both
    are bounded by `new_words`, the words of the amendment's new text.
    """

    amendment_id: AmendmentId
    kind: MatchKind = "verbatim"
    stage: AmendmentStage
    committee: str | None = None
    author_ids: tuple[ActorId, ...] = ()
    author_names: tuple[str, ...] = ()
    # The political group of each author, in the same order as `author_ids`; None where the
    # author's group is unknown. Empty when there are no author IDs.
    author_groups: tuple[str | None, ...] = ()
    tabled_on: date | None = None
    phrase_ids: tuple[PhraseId, ...] = Field(min_length=1)
    adopted_words: int = Field(ge=1)
    inserted_words: int = Field(ge=1)
    new_words: int = Field(ge=1)
    longest_run: int = Field(ge=1)
    evidence: tuple[AdoptionEvidence, ...] = ()

    @model_validator(mode="after")
    def adoption_fits_inside_the_new_text(self) -> Self:
        if self.author_groups and len(self.author_groups) != len(self.author_ids):
            raise ValueError("`author_groups` gives one group per author ID")
        if self.adopted_words > self.new_words or self.inserted_words > self.new_words:
            raise ValueError("An amendment cannot adopt or insert more words than it holds")
        if self.longest_run > self.adopted_words:
            raise ValueError("The longest run cannot exceed the adopted words")
        return self


class Credit(FrozenModel):
    """The adopted wording one holder is credited with, and the amendments behind it.

    No fractional credit (`docs/plan.md` section 7): every holder of a phrase is credited
    with the whole phrase, and `joint_phrases` counts those it shares with another holder of
    its kind. `amendments` is how many of the holder's amendments reached the final act and
    `amendments_tabled` how many it tabled on this law, both counting a committee amendment
    and its identical plenary re-tabling once, so the rate is "N of M". A holder is a Member
    (`mep`), a political group (through its Members, or named as the tabler), an author name
    that resolved to no actor (`unresolved`), or `committee_text` when an amendment names no
    author and no other carrier of the phrase does.
    """

    holder_id: NonEmpty
    basis: MatchKind = "verbatim"
    holder_kind: HolderKind
    name: NonEmpty
    phrases: int = Field(ge=1)
    joint_phrases: int = Field(ge=0)
    amendments: int = Field(ge=0)
    amendments_tabled: int = Field(ge=1)

    @property
    def rate(self) -> float:
        """Share of the holder's tabled amendments that reached the final act."""
        return self.amendments / self.amendments_tabled

    @model_validator(mode="after")
    def counts_fit(self) -> Self:
        if self.joint_phrases > self.phrases:
            raise ValueError("Joint phrases cannot exceed the phrases credited")
        if self.amendments > self.amendments_tabled:
            raise ValueError("A holder cannot have more adopting amendments than it tabled")
        return self


def credit_rank(credit: Credit) -> tuple[bool, int, float, int, int, str]:
    """Order of the credit table: verbatim before semantic, by kind, then rate per amendment.

    Members are ranked only by that rate (`docs/plan.md` section 7); ties go to the larger
    denominator, then more phrases, then the identifier, so the order is reproducible.
    """
    return (
        credit.basis == "semantic",
        _KIND_ORDER[credit.holder_kind],
        -credit.rate,
        -credit.amendments_tabled,
        -credit.phrases,
        credit.holder_id,
    )


class OriginMatch(FrozenModel):
    """A consultation document that says the adopted wording too, with the dates compared."""

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
    # The earliest tabling date of the carrying amendments; None when any of them is
    # undated, since the undated one may have come first.
    earliest_amendment_on: date | None = None
    # None when a date is unknown: an undated document, or carrier, cannot settle the order.
    precedes: bool | None = None
    # Explicit date status for the same fact: did the consultation document come first?
    eligibility: TimeEligibility = "unknown_date"
    # A run that is a citation of another act ("... of the European Parliament and of the
    # Council of 20 May 2021 ...") is shared wording but not a request.
    is_citation: bool = False
    supports: tuple[OriginSupport, ...] = ()

    @property
    def counts_as_origin(self) -> bool:
        """Only a dated document that came first and is not a citation counts as an origin."""
        return self.eligibility == "ask_first" and not self.is_citation

    @model_validator(mode="after")
    def eligibility_follows_the_dates(self) -> Self:
        if self.eligibility != _ELIGIBILITY[self.precedes]:
            raise ValueError("`eligibility` must follow `precedes`")
        return self


class LineageCounts(FrozenModel):
    """Sizes the reader needs to judge a result against how much the law changed.

    `changed_units` counts the words of the final act that stand in a window the proposal
    lacks and `linked_units` those of them inside an adopted phrase, so coverage is linked
    over changed and a law that barely changed says so instead of looking like a failure.
    A count is None until it has been computed (no proposal or final act, no documents
    read), never zero. `phrases_without_group` counts adopted phrases none of whose holders
    has a known political group: they are left out of the group credits and counted here.
    `documents_with_origin` counts documents with a match that counts as an origin
    (`OriginMatch.counts_as_origin`).
    """

    amendments: int = Field(ge=0)
    amendments_adopting: int | None = Field(default=None, ge=0)
    adopted_phrases: int | None = Field(default=None, ge=0)
    phrases_without_group: int | None = Field(default=None, ge=0)
    documents_read: int | None = Field(default=None, ge=0)
    documents_with_origin: int | None = Field(default=None, ge=0)
    changed_units: int | None = Field(default=None, ge=0)
    linked_units: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def parts_fit_inside_their_wholes(self) -> Self:
        pairs = (
            (self.linked_units, self.changed_units, "Linked units", "the units that changed"),
            (
                self.documents_with_origin,
                self.documents_read,
                "Documents with an origin",
                "the documents read",
            ),
        )
        for part, whole, part_name, whole_name in pairs:
            if part is not None and whole is not None and part > whole:
                raise ValueError(f"{part_name} cannot exceed {whole_name}")
        return self


class LineageView(FrozenModel):
    """Everything the explorer and the review need about one law's lineage."""

    schema_version: Literal["lineage-1", "lineage-2"] = LINEAGE_SCHEMA_VERSION
    procedure_id: ProcedureId
    slug: NonEmpty
    title: NonEmpty
    run_id: NonEmpty
    generated_at: AwareDatetime
    method: NonEmpty
    method_revision: NonEmpty
    coverage: tuple[LayerCoverage, ...] = ()
    # "unknown" when a layer adoption needs (the proposal or the final act) is missing;
    # `reason` then says which, and nothing is adopted or credited.
    status: AdoptionStatus = "computed"
    reason: str | None = None
    counts: LineageCounts
    adopted_phrases: tuple[AdoptedPhrase, ...] = ()
    tabled_phrases: tuple[TabledPhrase, ...] = ()
    adoptions: tuple[AmendmentAdoption, ...] = ()
    origins: tuple[OriginMatch, ...] = ()
    credits: tuple[Credit, ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def references_resolve(self) -> Self:
        if (self.status == "unknown") != (self.reason is not None):
            raise ValueError("An unknown adoption carries its reason, and only then")
        if self.status == "unknown" and (self.adopted_phrases or self.adoptions or self.credits):
            raise ValueError("An unknown adoption lists no phrases, adoptions or credits")
        adopted = {phrase.phrase_id for phrase in self.adopted_phrases}
        tabled = {phrase.phrase_id for phrase in self.tabled_phrases}
        if len(adopted) != len(self.adopted_phrases) or len(tabled) != len(self.tabled_phrases):
            raise ValueError("Duplicate phrase identifiers")
        if adopted & tabled:
            raise ValueError("A phrase is adopted or only tabled, not both")
        carriers: dict[str, set[str]] = {phrase_id: set() for phrase_id in adopted | tabled}
        for adoption in self.adoptions:
            if not set(adoption.phrase_ids) <= adopted:
                raise ValueError(f"{adoption.amendment_id} names a phrase that is not listed")
            for phrase_id in adoption.phrase_ids:
                carriers[phrase_id].add(adoption.amendment_id)
        for phrase in self.tabled_phrases:
            carriers[phrase.phrase_id] |= set(phrase.amendment_ids)
        for origin in self.origins:
            if origin.phrase_id not in carriers:
                raise ValueError(f"{origin.document_id} names a phrase that is not listed")
            if not set(origin.amendment_ids) <= carriers[origin.phrase_id]:
                raise ValueError("An origin names an amendment that does not carry its phrase")
        evidence_by_id: dict[str, tuple[AmendmentAdoption, AdoptionEvidence]] = {}
        phrases = {phrase.phrase_id: phrase for phrase in self.adopted_phrases}
        for adoption in self.adoptions:
            if (
                self.schema_version == "lineage-2"
                and adoption.kind == "verbatim"
                and {item.phrase_id for item in adoption.evidence} != set(adoption.phrase_ids)
            ):
                raise ValueError("A lineage-2 adoption needs carrier evidence for every phrase")
            for evidence in adoption.evidence:
                if evidence.evidence_id in evidence_by_id:
                    raise ValueError("Duplicate adoption evidence identifiers")
                if (
                    adoption.kind != "verbatim"
                    or evidence.amendment_span.record_id != adoption.amendment_id
                    or evidence.phrase_id not in adoption.phrase_ids
                ):
                    raise ValueError("Carrier evidence must reference its own amendment and phrase")
                phrase = phrases[evidence.phrase_id]
                if phrase.kind != "verbatim":
                    raise ValueError("Carrier evidence references only verbatim adopted phrases")
                containing = [
                    span
                    for span in phrase.final_spans
                    if (
                        span.record_id == evidence.final_span.record_id
                        and span.start <= evidence.final_span.start
                        and evidence.final_span.end <= span.end
                    )
                ]
                if not containing:
                    raise ValueError("Carrier evidence names no listed final occurrence")
                _span_word_interval(containing[0], evidence.final_span)
                evidence_by_id[evidence.evidence_id] = (adoption, evidence)
        support_ids: set[str] = set()
        for origin in self.origins:
            exact_adopted = origin.phrase_id in adopted and origin.kind == "verbatim"
            if self.schema_version == "lineage-2" and exact_adopted and not origin.supports:
                raise ValueError("A lineage-2 adopted verbatim origin needs exact carrier supports")
            if not origin.supports:
                continue
            if not exact_adopted:
                raise ValueError("Carrier supports belong only to adopted verbatim origins")
            dates: dict[str, date | None] = {}
            for support in origin.supports:
                if support.support_id in support_ids:
                    raise ValueError("Duplicate origin support identifiers")
                support_ids.add(support.support_id)
                carrier = evidence_by_id.get(support.adoption_evidence_id)
                if carrier is None:
                    raise ValueError("An origin support names missing adoption evidence")
                adoption, evidence = carrier
                if (
                    support.amendment_id != adoption.amendment_id
                    or origin.phrase_id != evidence.phrase_id
                    or support.submission_span != origin.span
                    or support.submission_span.record_id != origin.document_id
                ):
                    raise ValueError(
                        "An origin support must reference its exact origin and carrier"
                    )
                interval = _span_word_interval(evidence.amendment_span, support.amendment_span)
                if interval != _span_word_interval(evidence.final_span, support.final_span):
                    raise ValueError(
                        "Amendment and final projections must align inside the carrier run"
                    )
                if not any(
                    interval[0] <= offset < interval[1] for offset in evidence.inserted_word_offsets
                ):
                    raise ValueError("An origin support must intersect an inserted word")
                dates[adoption.amendment_id] = adoption.tabled_on
            if origin.amendment_ids != tuple(sorted(dates)):
                raise ValueError("An origin names exactly the amendments its supports carry")
            if origin.words != len(_folded_words(origin.span.text)):
                raise ValueError("Origin word count must equal its exact supported quote")
            earliest = (
                None
                if any(day is None for day in dates.values())
                else min(day for day in dates.values() if day is not None)
            )
            precedes = (
                None
                if earliest is None or origin.published_at is None
                else (origin.published_at.date() < earliest)
            )
            if (origin.earliest_amendment_on, origin.precedes) != (earliest, precedes):
                raise ValueError("An origin's chronology uses only its supported carriers")
        if list(self.credits) != sorted(self.credits, key=credit_rank):
            raise ValueError("Credits are listed in `credit_rank` order")
        return self


class LineageLawSummary(FrozenModel):
    """One law with a written lineage view, as the explorer's law list shows it.

    A count is None when the view could not compute it, as in `LineageCounts`.
    """

    slug: NonEmpty
    procedure_id: ProcedureId
    title: NonEmpty
    run_id: NonEmpty
    status: AdoptionStatus
    adopted_phrases: int | None = Field(ge=0)
    amendments_adopting: int | None = Field(ge=0)
    documents_with_origin: int | None = Field(ge=0)


class LineageLawList(FrozenModel):
    laws: tuple[LineageLawSummary, ...]


__all__ = [
    "COALITION_GROUPS",
    "LINEAGE_SCHEMA_VERSION",
    "MIN_ADOPTED_RUN_WORDS",
    "NGRAM_WORDS",
    "AdoptedPhrase",
    "AdoptionEvidence",
    "AmendmentAdoption",
    "Credit",
    "LineageCounts",
    "LineageLawList",
    "LineageLawSummary",
    "LineageView",
    "OriginMatch",
    "OriginSupport",
    "TabledPhrase",
    "credit_rank",
]
