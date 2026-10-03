"""Part 4 for prose: which of an amendment's changed words a submission passage shares.

The edit scorer compares two edits, so it fits LobbyPlag's clean old and new wording. A
submission passage is prose of dozens of words around the few the lobbyist wants, and
against prose a symmetric overlap cannot rise above the changed words' share of the
passage, while a "not" anywhere in the passage looks like a reversal. This module asks the
question that does fit prose: how much of what the amendment changes appears in the passage
as the same phrase? A word shared on its own proves nothing (any passage holds "shall"), so
only runs of consecutive words count, and each word is weighted by how rare it is in the
passages of the same law, so boilerplate such as "high-risk AI systems" is worth little.

Runs are found greedily, longest first, each amendment word used once. O(r * n * m) for r
runs over n amendment words and m passage words, bounded to a few hundred words a side.
"""

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from re import Match

from influence.schemas.scoring import TOKEN_PATTERN

MIN_RUN_WORDS = 3
_NEGATIONS = frozenset({"not", "no", "never", "neither", "nor", "without", "cannot"})
# A sentence ends at . ! ? or ; followed by a space or a line feed, or at a line feed.
_SENTENCE_END = re.compile("[.!?;][ \N{LINE FEED}]|\N{LINE FEED}")


@dataclass(frozen=True, slots=True)
class Word:
    """A word of a text: its folded form and its half-open code-point offsets."""

    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SharedRun:
    """Consecutive words the amendment and the passage have in common."""

    amendment_first: int
    passage_first: int
    length: int
    weight: float


@dataclass(frozen=True, slots=True)
class ProseMatch:
    """What an amendment's changed words and a passage share, weighted by rarity."""

    runs: tuple[SharedRun, ...]
    coverage: float
    longest: int
    shared_weight: float


def words_of(text: str) -> tuple[Word, ...]:
    """The alphanumeric tokens of `text`, case-folded, with their offsets."""

    def folded(token: Match[str]) -> Word:
        return Word(token.group().casefold(), token.start(), token.end())

    return tuple(
        folded(token)
        for token in TOKEN_PATTERN.finditer(text)
        if any(char.isalnum() for char in token.group())
    )


def rarity_weights(texts: Iterable[str]) -> dict[str, float]:
    """Inverse document frequency of every word over `texts`, one text per passage.

    A word in every passage weighs about 0; a word in one of N passages weighs log(N + 1).
    Words not in the table are as rare as it gets (see `weight_of`).
    """
    frequency: Counter[str] = Counter()
    total = 0
    for text in texts:
        total += 1
        frequency.update({word.text for word in words_of(text)})
    return {word: math.log((total + 1) / (count + 0.5)) for word, count in frequency.items()}


def weight_of(word: str, rarity: Mapping[str, float] | None) -> float:
    """1 with no table; otherwise the word's weight, or the rarest known for an unseen word."""
    if rarity is None:
        return 1.0
    return rarity[word] if word in rarity else max(rarity.values(), default=1.0)


def _longest_common_run(
    amendment: Sequence[str], taken: Sequence[bool], passage: Sequence[str]
) -> tuple[int, int, int]:
    """(amendment index, passage index, length) of the longest unused common run."""
    best = (0, 0, 0)
    previous = [0] * (len(passage) + 1)
    for i in range(1, len(amendment) + 1):
        current = [0] * (len(passage) + 1)
        if not taken[i - 1]:
            for j in range(1, len(passage) + 1):
                if amendment[i - 1] == passage[j - 1]:
                    current[j] = previous[j - 1] + 1
                    if current[j] > best[2]:
                        best = (i - current[j], j - current[j], current[j])
        previous = current
    return best


def _sentence_at(text: str, offset: int) -> str:
    """The sentence of `text` holding `offset`: up to the nearest ender on each side."""
    start = max((end.end() for end in _SENTENCE_END.finditer(text, 0, offset)), default=0)
    ender = _SENTENCE_END.search(text, offset)
    return text[start : len(text) if ender is None else ender.start() + 1]


def negation_conflict(
    amendment_text: str, amendment_offset: int, passage_text: str, passage_offset: int
) -> bool:
    """True when exactly one of the two sentences holding a shared phrase is negated.

    "Providers shall keep logs for six months" against "providers shall not keep logs for
    six months" shares a phrase and means the opposite. A "not" in another sentence of a
    long passage is not a conflict, which is what a whole-passage check got wrong.
    """

    def negated(text: str, offset: int) -> bool:
        return any(word.text in _NEGATIONS for word in words_of(_sentence_at(text, offset)))

    return negated(amendment_text, amendment_offset) != negated(passage_text, passage_offset)


def match_prose(
    amendment_words: Sequence[str],
    passage_words: Sequence[str],
    rarity: Mapping[str, float] | None = None,
) -> ProseMatch:
    """Share of the amendment's changed words found as phrases in the passage.

    `coverage` is the rarity-weighted fraction of `amendment_words` inside shared runs of at
    least `MIN_RUN_WORDS`.
    """
    taken = [False] * len(amendment_words)
    runs: list[SharedRun] = []
    while True:
        first, other, length = _longest_common_run(amendment_words, taken, passage_words)
        if length < MIN_RUN_WORDS:
            break
        for index in range(first, first + length):
            taken[index] = True
        weight = sum(weight_of(word, rarity) for word in amendment_words[first : first + length])
        runs.append(SharedRun(first, other, length, weight))
    total = sum(weight_of(word, rarity) for word in amendment_words)
    shared = sum(run.weight for run in runs)
    return ProseMatch(
        runs=tuple(sorted(runs, key=lambda run: run.amendment_first)),
        coverage=min(1.0, shared / total) if total > 0 else 0.0,
        longest=max((run.length for run in runs), default=0),
        shared_weight=shared,
    )
