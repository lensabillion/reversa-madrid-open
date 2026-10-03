"""Lineage, verbatim adoption: which new wording of the final act came from which amendments.

The first pipeline goes from a submission forward. This piece starts from the final act. A
run of consecutive words is adopted wording when it stands in the final act, is not in the
Commission's proposal, and an amendment inserted it. A run of twelve or more words cannot be
a coincidence, but it is still only evidence of shared wording: the final act is also shaped by
the Council and the trilogues, and the same run often sits in several amendments because they
were coordinated or co-signed. Nothing here says who wrote it first or why.

Method, all on lower-cased alphanumeric words (`prose_match.words_of`):

1. Every window of `NGRAM_WORDS` consecutive words of every proposal article goes into a set
   (the proposal's own wording), and every window of every final-act article into an index
   of where it stands.
2. For each amendment the inserted words are found with a word diff of old against new
   (the whole new text when the original is unknown), as blocks of consecutive inserted words.
3. Inside a block, a window counts when it is in the final act and not in the proposal.
   Consecutive such windows that also stand next to each other in the same final-act article
   (the same diagonal) merge into one run; a run of `MIN_ADOPTED_RUN_WORDS` or more is a phrase.
4. A phrase is identified by its folded text, so the same run in many amendments is one
   `AdoptedPhrase`, with exact spans in the final act.
5. Each phrase is worth 1, split equally among the holders credited for it: the MEPs who tabled
   an amendment carrying it, plus `committee_text` when one of those amendments has no author.
   A group's credit is the sum of its members' shares, so co-signers do not count twice.

Cost: building the indexes is linear in the words of the proposal and the final act; each
amendment costs its diff, O(n * m) for n and m words and bounded by `MAX_DIFF_WORDS`, plus one
lookup per inserted window. The AI Act (5,660 amendments, 712 final provisions) runs in
seconds.
"""

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from influence.schemas.atlas import Actor, Amendment, ArticleVersion, SourceSpan
from influence.schemas.lineage import (
    MIN_ADOPTED_RUN_WORDS,
    NGRAM_WORDS,
    AdoptedPhrase,
    AmendmentAdoption,
    Credit,
    HolderKind,
    LineageCounts,
)
from influence.services.pipeline import Collected
from influence.services.prose_match import Word, words_of

# A word diff is quadratic. Past this many words on either side the exact diff is replaced by
# "the new words that the old text does not contain", which finds the same runs here (the
# novelty test against the proposal does the real filtering) and is linear.
MAX_DIFF_WORDS = 3000
COMMITTEE_TEXT = "committee_text"
MAX_SPANS_PER_PHRASE = 3
UNKNOWN_GROUP = "unknown"

type Diagonal = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Adoption:
    """What was adopted, from whom, and how many amendments were looked at."""

    phrases: tuple[AdoptedPhrase, ...]
    adoptions: tuple[AmendmentAdoption, ...]
    credits: tuple[Credit, ...]
    amendments: int
    limitations: tuple[str, ...]

    @property
    def amendments_adopting(self) -> int:
        return len(self.adoptions)

    def counts(self, *, documents_read: int = 0, documents_with_origin: int = 0) -> LineageCounts:
        return LineageCounts(
            amendments=self.amendments,
            amendments_adopting=self.amendments_adopting,
            adopted_phrases=len(self.phrases),
            documents_read=documents_read,
            documents_with_origin=documents_with_origin,
        )


@dataclass(frozen=True, slots=True)
class _Run:
    """A phrase found in one amendment, with where it stands in the final act."""

    words: tuple[str, ...]
    places: tuple[tuple[int, int], ...]  # (final article index, first word index)
    start: int  # first word of the run inside its block of inserted words


def _windows(words: Sequence[str]) -> Iterable[tuple[int, tuple[str, ...]]]:
    for index in range(len(words) - NGRAM_WORDS + 1):
        yield index, tuple(words[index : index + NGRAM_WORDS])


def inserted_blocks(amendment: Amendment) -> tuple[tuple[list[str], ...], str]:
    """Blocks of consecutive inserted words, and how they were found.

    The second value is "exact", "unknown_original" or "approximate" so the caller can count
    how many amendments rest on a weaker basis.
    """
    new = [word.text for word in words_of(amendment.new_text)]
    if amendment.old_text is None:
        return (new,), "unknown_original"
    old = [word.text for word in words_of(amendment.old_text)]
    if len(old) > MAX_DIFF_WORDS or len(new) > MAX_DIFF_WORDS:
        known = set(old)
        blocks: list[list[str]] = []
        current: list[str] = []
        for word in new:
            if word in known:
                if current:
                    blocks.append(current)
                current = []
            else:
                current.append(word)
        if current:
            blocks.append(current)
        return tuple(blocks), "approximate"
    matcher = SequenceMatcher(None, old, new, autojunk=False)
    return (
        tuple(
            new[j1:j2]
            for tag, _, _, j1, j2 in matcher.get_opcodes()
            if tag in ("insert", "replace")
        ),
        "exact",
    )


def _runs(
    block: list[str],
    final_index: dict[tuple[str, ...], list[tuple[int, int]]],
    proposal: set[tuple[str, ...]],
) -> list[_Run]:
    """Maximal runs of windows that are novel, in the final act, and next to each other there."""
    runs: list[_Run] = []
    current: set[Diagonal] | None = None
    start = last = 0

    def close() -> None:
        length = last + NGRAM_WORDS - start
        if current and length >= MIN_ADOPTED_RUN_WORDS:
            places = tuple(sorted((article, start + shift) for article, shift in current))
            runs.append(_Run(tuple(block[start : last + NGRAM_WORDS]), places, start))

    for index, window in _windows(block):
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
            close()
        current = diagonals or None
        start = last = index
    if current is not None:
        close()
    return runs


def phrase_id_of(words: Sequence[str]) -> str:
    return "phrase:" + hashlib.sha256(" ".join(words).encode("utf-8")).hexdigest()[:16]


def _span(article: ArticleVersion, words: Sequence[Word], first: int, length: int) -> SourceSpan:
    start, end = words[first].start, words[first + length - 1].end
    return SourceSpan(
        record_id=article.article_id,
        field="text",
        start=start,
        end=end,
        text=article.text[start:end],
    )


def _holders(amendment: Amendment) -> tuple[str, ...]:
    return amendment.author_ids or (COMMITTEE_TEXT,)


def adopt_records(
    amendments: Sequence[Amendment],
    articles: Sequence[ArticleVersion],
    actors: Sequence[Actor],
) -> Adoption:
    """Find the adopted wording, the amendments that carry it and the credit for each holder."""
    proposal: set[tuple[str, ...]] = set()
    final_articles = [article for article in articles if article.stage == "final_act"]
    final_words = [words_of(article.text) for article in final_articles]
    final_index: dict[tuple[str, ...], list[tuple[int, int]]] = defaultdict(list)
    for article in articles:
        if article.stage == "proposal":
            proposal.update(
                window for _, window in _windows([w.text for w in words_of(article.text)])
            )
    for article_number, words in enumerate(final_words):
        for position, window in _windows([word.text for word in words]):
            final_index[window].append((article_number, position))

    carried: dict[str, _Run] = {}
    carriers: dict[str, list[str]] = defaultdict(list)
    adoptions: list[AmendmentAdoption] = []
    bases: defaultdict[str, int] = defaultdict(int)
    for amendment in amendments:
        blocks, basis = inserted_blocks(amendment)
        bases[basis] += 1
        found = [
            (number, run)
            for number, block in enumerate(blocks)
            for run in _runs(block, final_index, proposal)
        ]
        if not found:
            continue
        distinct = {phrase_id_of(run.words): run for _, run in found}
        for phrase_id, run in distinct.items():
            carried.setdefault(phrase_id, run)
            carriers[phrase_id].append(amendment.amendment_id)
        # Runs that switch final-act location overlap by up to NGRAM_WORDS - 1 words, so the
        # adopted words are the union of the positions the runs cover, never a sum of lengths.
        covered = {
            (number, position)
            for number, run in found
            for position in range(run.start, run.start + len(run.words))
        }
        adoptions.append(
            AmendmentAdoption(
                amendment_id=amendment.amendment_id,
                stage="committee" if amendment.stage == "committee" else "plenary",
                committee=amendment.committee,
                author_ids=amendment.author_ids,
                author_names=amendment.author_names,
                tabled_on=amendment.tabled_on,
                phrase_ids=tuple(sorted(distinct)),
                adopted_words=len(covered),
                inserted_words=sum(len(block) for block in blocks),
                longest_run=max(len(run.words) for run in distinct.values()),
            )
        )

    phrases = tuple(
        AdoptedPhrase(
            phrase_id=phrase_id,
            text=" ".join(run.words),
            words=len(run.words),
            final_spans=tuple(
                _span(final_articles[article], final_words[article], first, len(run.words))
                for article, first in run.places[:MAX_SPANS_PER_PHRASE]
            ),
        )
        for phrase_id, run in sorted(carried.items())
    )
    by_amendment = {amendment.amendment_id: amendment for amendment in amendments}
    credits = _credits(adoptions, by_amendment, actors, carriers)
    notes: list[str] = []
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
    return Adoption(phrases, tuple(adoptions), credits, len(amendments), tuple(notes))


def _credits(
    adoptions: Sequence[AmendmentAdoption],
    amendments: dict[str, Amendment],
    actors: Sequence[Actor],
    carriers: dict[str, list[str]],
) -> tuple[Credit, ...]:
    group_of = {actor.actor_id: actor.political_group or UNKNOWN_GROUP for actor in actors}
    name_of = {actor.actor_id: actor.name for actor in actors}
    phrase_share: defaultdict[str, float] = defaultdict(float)
    phrase_count: defaultdict[str, int] = defaultdict(int)
    kinds: dict[str, HolderKind] = {}
    names: dict[str, str] = {}
    holder_amendments: defaultdict[str, set[str]] = defaultdict(set)
    for amendment_ids in carriers.values():
        holders = sorted({h for a in amendment_ids for h in _holders(amendments[a])})
        share = 1 / len(holders)
        groups: defaultdict[str, float] = defaultdict(float)
        for holder in holders:
            if holder == COMMITTEE_TEXT:
                kinds[holder], names[holder] = "committee_text", "Committee text"
            else:
                kinds[holder] = "mep"
                names[holder] = name_of.get(holder, holder)
                groups[group_of.get(holder, UNKNOWN_GROUP)] += share
            phrase_share[holder] += share
            phrase_count[holder] += 1
        for group, total in groups.items():
            key = f"group:{group}"
            kinds[key], names[key] = "group", group
            phrase_share[key] += total
            phrase_count[key] += 1
    for adoption in adoptions:
        for holder in _holders(amendments[adoption.amendment_id]):
            holder_amendments[holder].add(adoption.amendment_id)
            if holder != COMMITTEE_TEXT:
                holder_amendments[f"group:{group_of.get(holder, UNKNOWN_GROUP)}"].add(
                    adoption.amendment_id
                )
    ordered = sorted(phrase_share, key=lambda key: (-phrase_share[key], key))
    return tuple(
        Credit(
            holder_id=key.removeprefix("group:"),
            holder_kind=kinds[key],
            name=names[key],
            phrases=phrase_share[key],
            distinct_phrases=phrase_count[key],
            amendments=len(holder_amendments[key]),
        )
        for key in ordered
    )


def adopt(collected: Collected) -> Adoption:
    """`adopt_records` over one collected law."""
    return adopt_records(collected.amendments, collected.articles, collected.actors)
