"""Contracts of the lineage pipeline: which wording of the final law came from where.

The Atlas pipeline goes from a submission to an amendment to the law. Lineage starts from the
law: it finds the stretches of the final act that were not in the Commission's proposal, finds
the amendments whose new text holds them, and then who tabled those amendments and which
consultation documents say the same thing earlier. It is a separate pipeline with its own
view (`lineage-1`) and leaves the `atlas-1` records untouched. The explorer reads this view
(`GET /api/v1/lineage/{slug}`, page `/lineage`); its claims stay labelled as unreviewed until
they pass the gates in `docs/design/`.

Pieces and who produces what:

* adoption (`services/lineage.py`, `adopt_records`): verbatim `AdoptedPhrase`,
  `AmendmentAdoption`, `Credit`. A phrase is a place in the final act (an article and a word
  interval), so one stretch of the law is never counted twice;
* origin (`services/origin.py`): `OriginMatch` for adopted phrases (`find_origins`) and for
  inserted wording whether or not it was adopted (`find_tabled_origins`, `TabledPhrase`).
  Origin and adoption are two independent facts: a document can be the origin of an
  amendment that was never adopted, and an adopted phrase can have no known origin;
* assembly (`services/lineage_assembly.py`, `build_lineage`, run by `influence lineage`):
  `LineageView`, written to `data/laws/<procedure>/lineage.json`;
* review (`practice/lineage_review.py`): reads a `LineageView`, never writes one.

The "semantic" kind (reworded wording found by embeddings and a judge) is part of the contract
but no piece produces it yet. A verbatim match is a run of identical words: cheap and nearly
unambiguous, and still only evidence of shared wording, not of who wrote it first or why.

Counting follows `docs/plan.md` section 7: no fractional credit (every holder of a phrase is
credited with the whole phrase, and a phrase with several holders is flagged joint), Members
are ranked by their rate per amendment tabled, and an unknown count is None, never zero.
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
from influence.schemas.scoring import FrozenModel

LINEAGE_SCHEMA_VERSION = "lineage-1"
# Phrases are found as runs of consecutive words; an 8-word window is the unit that is
# looked up, and a run must be at least this many words to count as shared wording. A run
# must also hold rare words (`services/lineage.Rarity`), so the law's own formulas do not
# count. Provisional: chosen by the owner on 3 October, not calibrated.
NGRAM_WORDS = 8
MIN_ADOPTED_RUN_WORDS = 8
# A phrase carried by amendments of at least this many different political groups is
# coalition wording rather than one group's request: the same rule as part 3's cross-group
# clusters (`services/coordinated.py`).
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
    # Part 4's name for the same fact: did the document (the ask) come first?
    eligibility: TimeEligibility = "unknown_date"
    # A run that is a citation of another act ("... of the European Parliament and of the
    # Council of 20 May 2021 ...") is shared wording but not a request.
    is_citation: bool = False

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
    `proposal_units` and `final_units` are the words of the whole proposal and final act,
    counted the same way, so the two texts compare in size whatever the provisions they are
    split into (a proposal split by article and a final act split by paragraph count
    differently).
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
    proposal_units: int | None = Field(default=None, ge=0)
    final_units: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def parts_fit_inside_their_wholes(self) -> Self:
        pairs = (
            (self.linked_units, self.changed_units, "Linked units", "the units that changed"),
            (self.changed_units, self.final_units, "Changed units", "the final act's units"),
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

    schema_version: Literal["lineage-1"] = LINEAGE_SCHEMA_VERSION
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
    "AmendmentAdoption",
    "Credit",
    "LineageCounts",
    "LineageLawList",
    "LineageLawSummary",
    "LineageView",
    "OriginMatch",
    "TabledPhrase",
    "credit_rank",
]
