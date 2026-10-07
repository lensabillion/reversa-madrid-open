"""Lineage, verbatim adoption: which new wording of the final act came from which amendments.

The first pipeline goes from a submission forward. This piece starts from the final act. A
stretch of the final act is adopted wording when it is not in the Commission's proposal and
an amendment's new text holds it as a run of `MIN_ADOPTED_RUN_WORDS` or more consecutive
words, at least one of them inserted by that amendment and at least `MIN_RARE_WORDS` of them
rare in the law (`Rarity`). Such a run is unlikely to be a coincidence or one of the law's own
formulas, but it is still only evidence of shared wording: the final act is also shaped by
the Council and the trilogues, and the same run often sits in several amendments because
they were coordinated or co-signed. Nothing here says who wrote it first or why.

Method, all on lower-cased alphanumeric words (`prose_match.words_of`):

1. Every window of `NGRAM_WORDS` consecutive words of every proposal article goes into a set
   (the proposal's own wording), and every window of every final-act article into an index
   of where it stands.
2. For each amendment a word diff of old against new marks the inserted words (every word
   when the original is unknown). Windows slide over the whole new text, so an insertion
   that rewrites half a sentence is not cut at the words it kept.
3. A window counts when it is in the final act and not in the proposal. Consecutive such
   windows that also stand next to each other in the same final-act article (the same
   diagonal) merge into one run; a run of `MIN_ADOPTED_RUN_WORDS` or more that holds an
   inserted word and is significant (`Rarity.significant`) is kept. Final-act renumbering
   ("Article 6(2)" becoming "Article 9(2)") makes formulas look new, which is what the
   rarity test removes.
4. The final-act words the kept runs cover, over all amendments, are merged into intervals.
   Each interval is one `AdoptedPhrase`, identified by its place (article and word
   interval), so overlapping runs never make two phrases out of one stretch of the law.
   The amendments that carry a phrase are those whose runs cover any word of it.
5. Credit follows `docs/plan.md` section 7: every holder of a phrase is credited with the
   whole phrase, and a phrase with several holders is joint. A holder is a Member who tabled
   a carrying amendment, the group an amendment names as its tabler when it has no
   resolved author, an author name that resolved to no actor, or the committee text when
   no carrier names an author. A group is credited once per phrase through its Members; an
   author whose group is unknown credits no group, and such phrases are counted apart.
   Amendments count once per distinct new text and holder, so a committee amendment and
   its identical plenary re-tabling are one, in the adopting count and in the tabled one.

Without a proposal or a final act nothing can be told apart, so the result is "unknown"
with its reason, never an empty success.

Cost: building the indexes is linear in the words of the proposal and the final act; each
amendment costs its diff, O(n * m) for n and m words and bounded by `MAX_DIFF_WORDS`, plus one
lookup per window of its new text. The AI Act (5,660 amendments, 712 final provisions) runs in
seconds.
"""

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Self

from influence.schemas.atlas import Actor, Amendment, ArticleVersion, SourceSpan
from influence.schemas.lineage import (
    MIN_ADOPTED_RUN_WORDS,
    NGRAM_WORDS,
    AdoptedPhrase,
    AdoptionStatus,
    AmendmentAdoption,
    Credit,
    HolderKind,
    LineageCounts,
    credit_rank,
)
from influence.services.collected import Collected
from influence.services.prose_match import Word, words_of
from influence.services.tabling_groups import group_limitations, latest_groups, tabling_groups

# A word diff is quadratic. Past this many words on either side the exact diff is replaced by
# "the new words that the old text does not contain", which finds the same runs here (the
# novelty test against the proposal does the real filtering) and is linear.
MAX_DIFF_WORDS = 3000
COMMITTEE_TEXT = "committee_text"
# A word is rare in a law when it stands in fewer than this share of its provisions (proposal
# and final act), or in only one. A run needs this many distinct rare words to count.
# Provisional values, chosen on 3 October without labelled data.
RARE_PROVISION_SHARE = 0.05
MIN_RARE_WORDS = 3
# "on behalf of the Verts/ALE Group" names the tabling group when no Member is resolved.
_GROUP_NAMED = re.compile(r"\bon behalf of the (.+?) group\b", re.IGNORECASE)

type Diagonal = tuple[int, int]
type Place = tuple[int, int]  # (final article index, word index)


@dataclass(frozen=True, slots=True)
class Adoption:
    """What was adopted, from whom, how many amendments were looked at, and the coverage.

    `status` is "unknown" when the proposal or the final act is missing; `reason` says which,
    and every count that depends on them stays None.
    """

    phrases: tuple[AdoptedPhrase, ...]
    adoptions: tuple[AmendmentAdoption, ...]
    credits: tuple[Credit, ...]
    amendments: int
    limitations: tuple[str, ...]
    status: AdoptionStatus = "computed"
    reason: str | None = None
    changed_units: int | None = None
    linked_units: int | None = None
    phrases_without_group: int | None = None

    @property
    def amendments_adopting(self) -> int | None:
        return None if self.status == "unknown" else len(self.adoptions)

    def counts(
        self, *, documents_read: int | None = None, documents_with_origin: int | None = None
    ) -> LineageCounts:
        return LineageCounts(
            amendments=self.amendments,
            amendments_adopting=self.amendments_adopting,
            adopted_phrases=None if self.status == "unknown" else len(self.phrases),
            phrases_without_group=self.phrases_without_group,
            documents_read=documents_read,
            documents_with_origin=documents_with_origin,
            changed_units=self.changed_units,
            linked_units=self.linked_units,
        )


@dataclass(frozen=True, slots=True)
class Rarity:
    """The words that are common in one law, so a run made of them is not shared wording.

    Document frequency is counted over provisions: a word in many provisions ("shall",
    "provider", "article") is common. Building it is linear in the law's words.
    """

    common: frozenset[str]

    @classmethod
    def of(cls, texts: Iterable[str]) -> Self:
        frequency: Counter[str] = Counter()
        provisions = 0
        for text in texts:
            provisions += 1
            frequency.update({word.text for word in words_of(text)})
        floor = max(2.0, RARE_PROVISION_SHARE * provisions)
        return cls(frozenset(word for word, count in frequency.items() if count >= floor))

    def significant(self, words: Sequence[str]) -> bool:
        """True when the run holds at least `MIN_RARE_WORDS` distinct rare words."""
        return len({word for word in words if word not in self.common}) >= MIN_RARE_WORDS


@dataclass(frozen=True, slots=True)
class _Run:
    """A run found in one amendment's new text, with where it stands in the final act."""

    words: tuple[str, ...]
    places: tuple[Place, ...]  # where its first word stands in the final act
    start: int  # its first word inside the amendment's new text


@dataclass(frozen=True, slots=True)
class _Holder:
    key: str
    kind: HolderKind
    name: str


def _windows(words: Sequence[str]) -> Iterable[tuple[int, tuple[str, ...]]]:
    for index in range(len(words) - NGRAM_WORDS + 1):
        yield index, tuple(words[index : index + NGRAM_WORDS])


def inserted_words(amendment: Amendment) -> tuple[list[str], list[bool], str]:
    """The new text's folded words, which of them were inserted, and how that was found.

    Callers slide windows over the whole new text and keep those holding an inserted word,
    so an insertion that rewrites half a sentence is not cut at the words it kept.

    The third value is "exact", "unknown_original" or "approximate" so the caller can count
    how many amendments rest on a weaker basis.
    """
    new = [word.text for word in words_of(amendment.new_text)]
    if amendment.old_text is None:
        return new, [True] * len(new), "unknown_original"
    old = [word.text for word in words_of(amendment.old_text)]
    if len(old) > MAX_DIFF_WORDS or len(new) > MAX_DIFF_WORDS:
        known = set(old)
        return new, [word not in known for word in new], "approximate"
    mask = [False] * len(new)
    for tag, _, _, j1, j2 in SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag in ("insert", "replace"):
            mask[j1:j2] = [True] * (j2 - j1)
    return new, mask, "exact"


def _runs(
    words: list[str],
    inserted: list[bool],
    final_index: dict[tuple[str, ...], list[Place]],
    proposal: set[tuple[str, ...]],
    rarity: Rarity,
    dropped: list[int],
) -> list[_Run]:
    """Maximal runs of windows that are novel, in the final act, and next to each other there.

    A run is kept only when it holds a word the amendment inserted. A run long enough but
    made of the law's common words is not kept; `dropped` counts it.
    """
    runs: list[_Run] = []
    current: set[Diagonal] | None = None
    start = last = 0

    def close(run: set[Diagonal]) -> None:
        # Every run is at least one window long, and a window is `MIN_ADOPTED_RUN_WORDS`
        # words, so no length test is needed; the `AdoptedPhrase` contract refuses a shorter
        # phrase loudly if a larger minimum is ever set without one.
        end = last + NGRAM_WORDS
        if not any(inserted[start:end]):
            return
        found = tuple(words[start:end])
        if not rarity.significant(found):
            dropped[0] += 1
            return
        places = tuple(sorted((article, start + shift) for article, shift in run))
        runs.append(_Run(found, places, start))

    for index, window in _windows(words):
        diagonals: set[Diagonal] = (
            set()
            if window in proposal
            else {(article, position - index) for article, position in final_index.get(window, ())}
        )
        if current is not None and current & diagonals:
            current &= diagonals
            last = index
            continue
        if current is not None:
            close(current)
        current = diagonals or None
        start = last = index
    if current is not None:
        close(current)
    return runs


def phrase_id_of(words: Sequence[str]) -> str:
    """Identity of wording by its text: tabled wording, which has no place in the final act."""
    return "phrase:" + hashlib.sha256(" ".join(words).encode("utf-8")).hexdigest()[:16]


def _place_id(article_id: str, first: int, end: int) -> str:
    """Identity of adopted wording by its place, so one stretch of the law is one phrase."""
    key = f"place:{article_id}:{first}:{end}"
    return "phrase:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _span(article: ArticleVersion, words: Sequence[Word], first: int, end: int) -> SourceSpan:
    start, stop = words[first].start, words[end - 1].end
    return SourceSpan(
        record_id=article.article_id,
        field="text",
        start=start,
        end=stop,
        text=article.text[start:stop],
    )


def _intervals(places: Iterable[Place]) -> list[tuple[int, int, int]]:
    """Distinct places merged into (article, first, end) intervals of consecutive words."""
    merged: list[tuple[int, int, int]] = []
    for article, position in sorted(set(places)):
        if merged and merged[-1][0] == article and merged[-1][2] == position:
            merged[-1] = (article, merged[-1][1], position + 1)
        else:
            merged.append((article, position, position + 1))
    return merged


def _holders(amendment: Amendment, name_of: dict[str, str]) -> tuple[_Holder, ...]:
    """Who tabled the amendment, from the most to the least precise record of it."""
    if amendment.author_ids:
        return tuple(
            _Holder(author, "mep", name_of.get(author, author)) for author in amendment.author_ids
        )
    if amendment.author_names:
        found: list[_Holder] = []
        for name in amendment.author_names:
            named = _GROUP_NAMED.search(name)
            if named is not None:
                group = named.group(1).strip()
                found.append(_Holder(f"group:{group}", "group", group))
            else:
                found.append(_Holder(f"name:{name}", "unresolved", name))
        return tuple(found)
    return (_Holder(COMMITTEE_TEXT, "committee_text", "Committee text"),)


def _unknown(amendments: int, reason: str) -> Adoption:
    return Adoption((), (), (), amendments, (), status="unknown", reason=reason)


def adopt_records(
    amendments: Sequence[Amendment],
    articles: Sequence[ArticleVersion],
    actors: Sequence[Actor],
) -> Adoption:
    """Find the adopted wording, the amendments that carry it and the credit for each holder."""
    final_articles = [article for article in articles if article.stage == "final_act"]
    if not final_articles:
        return _unknown(
            len(amendments), "The final act's text was not collected; nothing can be traced."
        )
    proposal_articles = [article for article in articles if article.stage == "proposal"]
    if not proposal_articles:
        return _unknown(
            len(amendments),
            "The Commission proposal's text was not collected; new wording cannot be told "
            "from the proposal's.",
        )
    proposal: set[tuple[str, ...]] = set()
    for article in proposal_articles:
        proposal.update(window for _, window in _windows([w.text for w in words_of(article.text)]))
    final_words = [words_of(article.text) for article in final_articles]
    final_index: dict[tuple[str, ...], list[Place]] = defaultdict(list)
    changed: set[Place] = set()
    for article_number, words in enumerate(final_words):
        for position, window in _windows([word.text for word in words]):
            final_index[window].append((article_number, position))
            if window not in proposal:
                changed.update((article_number, position + k) for k in range(NGRAM_WORDS))

    rarity = Rarity.of(article.text for article in articles)
    dropped = [0]
    found: list[tuple[Amendment, set[Place], int, int, int, int]] = []
    bases: defaultdict[str, int] = defaultdict(int)
    for amendment in amendments:
        new, mask, basis = inserted_words(amendment)
        bases[basis] += 1
        kept = _runs(new, mask, final_index, proposal, rarity, dropped)
        if not kept:
            continue
        places = {
            (article, first + offset)
            for run in kept
            for article, first in run.places
            for offset in range(len(run.words))
        }
        # Runs that switch final-act location overlap by up to NGRAM_WORDS - 1 words, so the
        # adopted words are the union of the positions the runs cover, never a sum of lengths.
        covered = {
            position for run in kept for position in range(run.start, run.start + len(run.words))
        }
        longest = max(len(run.words) for run in kept)
        found.append((amendment, places, len(covered), sum(mask), len(new), longest))

    intervals = _intervals(place for _, places, *_ in found for place in places)
    phrase_of: dict[Place, int] = {}
    for number, (article, first, end) in enumerate(intervals):
        for position in range(first, end):
            phrase_of[article, position] = number
    phrase_ids = [
        _place_id(final_articles[article].article_id, first, end)
        for article, first, end in intervals
    ]
    carriers: list[list[Amendment]] = [[] for _ in intervals]
    latest = latest_groups(actors)
    adoptions: list[AmendmentAdoption] = []
    for amendment, places, adopted, inserted, new_words, longest in found:
        numbers = sorted({phrase_of[place] for place in places})
        for number in numbers:
            carriers[number].append(amendment)
        adoptions.append(
            AmendmentAdoption(
                amendment_id=amendment.amendment_id,
                stage="committee" if amendment.stage == "committee" else "plenary",
                committee=amendment.committee,
                author_ids=amendment.author_ids,
                author_names=amendment.author_names,
                author_groups=tuple(
                    tabling_groups(amendment, latest)[author] for author in amendment.author_ids
                ),
                tabled_on=amendment.tabled_on,
                phrase_ids=tuple(sorted(phrase_ids[number] for number in numbers)),
                adopted_words=adopted,
                inserted_words=inserted,
                new_words=new_words,
                longest_run=longest,
            )
        )

    credits, holders, ungrouped = _credits(carriers, amendments, actors)
    phrases = tuple(
        sorted(
            (
                AdoptedPhrase(
                    phrase_id=phrase_ids[number],
                    text=" ".join(word.text for word in final_words[article][first:end]),
                    words=end - first,
                    final_spans=(_span(final_articles[article], final_words[article], first, end),),
                    holders=holders[number],
                )
                for number, (article, first, end) in enumerate(intervals)
            ),
            key=lambda phrase: phrase.phrase_id,
        )
    )
    notes = list(group_limitations(amendments))
    if dropped[0]:
        notes.append(
            f"{dropped[0]} run(s) of {MIN_ADOPTED_RUN_WORDS} or more words were not counted: "
            f"they hold fewer than {MIN_RARE_WORDS} of the law's rare words."
        )
    if bases["unknown_original"]:
        notes.append(
            f"{bases['unknown_original']} amendment(s) have no original wording; their whole "
            "text was treated as inserted."
        )
    if bases["approximate"]:
        notes.append(
            f"{bases['approximate']} amendment(s) were too long for an exact diff; the new words "
            "their original lacks were treated as inserted."
        )
    if ungrouped:
        notes.append(
            f"{ungrouped} adopted phrase(s) have no holder with a known political group; they "
            "are left out of the group credits."
        )
    return Adoption(
        phrases,
        tuple(adoptions),
        credits,
        len(amendments),
        tuple(notes),
        changed_units=len(changed),
        linked_units=len(phrase_of),
        phrases_without_group=ungrouped,
    )


def _credits(
    carriers: Sequence[Sequence[Amendment]],
    amendments: Sequence[Amendment],
    actors: Sequence[Actor],
) -> tuple[tuple[Credit, ...], list[tuple[str, ...]], int]:
    """Whole-phrase credit per holder, each phrase's tablers, and phrases with no group.

    Linear in the carriers and amendments.
    """
    latest = latest_groups(actors)
    group_on_day = {a.amendment_id: tabling_groups(a, latest) for a in amendments}
    name_of = {actor.actor_id: actor.name for actor in actors}
    holders_of = {a.amendment_id: _holders(a, name_of) for a in amendments}
    # A committee amendment and its plenary re-tabling with the same words are one.
    text_of = {a.amendment_id: " ".join(w.text for w in words_of(a.new_text)) for a in amendments}
    names: dict[str, tuple[HolderKind, str]] = {}

    def keys(amendment_id: str) -> set[str]:
        found: set[str] = set()
        for holder in holders_of[amendment_id]:
            found.add(holder.key)
            names[holder.key] = (holder.kind, holder.name)
            group = group_on_day[amendment_id].get(holder.key) if holder.kind == "mep" else None
            if group is not None:
                found.add(f"group:{group}")
                names[f"group:{group}"] = ("group", group)
        return found

    tabled: defaultdict[str, set[str]] = defaultdict(set)
    for amendment in amendments:
        for key in keys(amendment.amendment_id):
            tabled[key].add(text_of[amendment.amendment_id])

    phrases: defaultdict[str, int] = defaultdict(int)
    joint: defaultdict[str, int] = defaultdict(int)
    adopting: defaultdict[str, set[str]] = defaultdict(set)
    tablers_of: list[tuple[str, ...]] = []
    ungrouped = 0
    for carrying in carriers:
        tablers = {h.key for a in carrying for h in holders_of[a.amendment_id]}
        if tablers - {COMMITTEE_TEXT}:
            tablers.discard(COMMITTEE_TEXT)
        # A Member's known group, or a group named as the tabler; never an "unknown" group.
        groups = {key for a in carrying for key in keys(a.amendment_id) if names[key][0] == "group"}
        if not groups:
            ungrouped += 1
        tablers_of.append(tuple(sorted(tablers)))
        for key in tablers | groups:
            phrases[key] += 1
            same_kind = groups if key in groups else tablers
            joint[key] += len(same_kind) > 1
        for amendment in carrying:
            for key in keys(amendment.amendment_id) & (tablers | groups):
                adopting[key].add(text_of[amendment.amendment_id])
    credits = sorted(
        (
            Credit(
                holder_id=key.removeprefix("group:"),
                holder_kind=names[key][0],
                name=names[key][1],
                phrases=count,
                joint_phrases=joint[key],
                amendments=len(adopting[key]),
                amendments_tabled=len(tabled[key]),
            )
            for key, count in phrases.items()
        ),
        key=credit_rank,
    )
    return tuple(credits), tablers_of, ungrouped


def adopt(collected: Collected) -> Adoption:
    """`adopt_records` over one collected law."""
    return adopt_records(collected.amendments, collected.articles, collected.actors)
