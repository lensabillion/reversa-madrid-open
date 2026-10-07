"""A per-law BM25 index over submission passages for optional lineage origin matching.

Retrieval only narrows the search. A high score means shared rare words, not influence.
"""

import re
from collections import Counter, defaultdict
from math import log

import numpy as np

from influence.schemas.retrieval import PassageCandidate, QueryKind, Shortlist, SourcePassage
from influence.schemas.scoring import TOKEN_PATTERN, TextChange
from influence.services.scoring import changed_spans

MAX_PASSAGE_TOKENS = 120
_K1 = 1.2
_B = 0.75
_SEGMENT = re.compile(r"\S.*?(?:[.!?;](?=\s|$)|\n\s*\n|$)", re.DOTALL)

_DELTA_LIMITATIONS = (
    "BM25 ranks passages by shared rare words; it is not a probability of influence.",
    "Only inserted and deleted words are searched, so wording shared with the original law "
    "is ignored. A paraphrase with no shared words is not retrieved.",
)
_WHOLE_TEXT_LIMITATIONS = (
    "BM25 ranks passages by shared rare words; it is not a probability of influence.",
    "The original wording is unknown, so the whole proposed text was searched. Wording "
    "copied from the existing law can match, and no change was inferred.",
)


def _words(text: str) -> list[str]:
    return [
        token.casefold() for token in TOKEN_PATTERN.findall(text) if any(c.isalnum() for c in token)
    ]


def split_passages(document_id: str, text: str) -> tuple[SourcePassage, ...]:
    """Pack sentences into non-overlapping passages of at most MAX_PASSAGE_TOKENS tokens.

    A sentence longer than the limit is cut at token boundaries rather than truncated, so
    every character of the document belongs to some passage. Linear in the text length.
    """
    units: list[tuple[int, int, int]] = []
    for segment in _SEGMENT.finditer(text):
        start, end = segment.start(), segment.start() + len(segment.group().rstrip())
        tokens = tuple(TOKEN_PATTERN.finditer(text, start, end))
        for first in range(0, len(tokens), MAX_PASSAGE_TOKENS):
            chunk = tokens[first : first + MAX_PASSAGE_TOKENS]
            units.append((chunk[0].start(), chunk[-1].end(), len(chunk)))
    passages: list[SourcePassage] = []
    start = end = size = 0
    for unit_start, unit_end, unit_size in units:
        if size and size + unit_size > MAX_PASSAGE_TOKENS:
            passages.append(
                SourcePassage(document_id=document_id, start=start, end=end, text=text[start:end])
            )
            size = 0
        if not size:
            start = unit_start
        end, size = unit_end, size + unit_size
    if size:
        passages.append(
            SourcePassage(document_id=document_id, start=start, end=end, text=text[start:end])
        )
    return tuple(passages)


class PassageIndex:
    """Inverted index over the passages of one law's submissions.

    A posting's BM25 weight depends only on the index (its term's rarity and its passage's
    length), never on the query, so it is computed once here, and a query adds whole weight
    arrays with numpy. Walking postings one at a time in Python took 212 s for the AI Act's
    5,660 amendments over 29,056 passages, because common words such as "the" have postings
    in most passages. Scores, ranks and tie-breaks are bit-identical to that walk: each
    passage still sums its terms' weights in sorted term order with the same float operations.

    Build is linear in total tokens. A query costs one vectorized add per distinct term over
    its postings, O(N) to collect the M matching passages among N, and O(M) to keep the top
    k (O(M log M) only when scores tie at the cut).
    """

    def __init__(self, passages: tuple[SourcePassage, ...]) -> None:
        self._passages = passages
        counts = [Counter(_words(passage.text)) for passage in passages]
        self._terms = [frozenset(count) for count in counts]
        lengths = [count.total() for count in counts]
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for index, count in enumerate(counts):
            for term, occurrences in count.items():
                postings[term].append((index, occurrences))
        total = len(passages)
        average = sum(lengths) / total if total else 0.0
        self._spans: dict[str, tuple[int, int]] = {}
        indices: list[int] = []
        frequencies: list[int] = []
        idfs: list[float] = []
        for term, entries in postings.items():
            # math.log, not numpy's, so each weight matches the per-posting walk to the bit.
            idf = log(1 + (total - len(entries) + 0.5) / (len(entries) + 0.5))
            self._spans[term] = (len(indices), len(indices) + len(entries))
            for index, occurrences in entries:
                indices.append(index)
                frequencies.append(occurrences)
                idfs.append(idf)
        self._indices = np.array(indices, dtype=np.intp)
        count_array = np.array(frequencies, dtype=np.float64)
        norm = 1 - _B + _B * np.array(lengths, dtype=np.float64)[self._indices] / average
        self._weights = np.array(idfs) * count_array * (_K1 + 1) / (count_array + _K1 * norm)

    def _context(self, index: int) -> tuple[int, int]:
        document = self._passages[index].document_id
        first = index - 1 if index and self._passages[index - 1].document_id == document else index
        after = index + 1
        last = (
            after
            if after < len(self._passages) and self._passages[after].document_id == document
            else index
        )
        return self._passages[first].start, self._passages[last].end

    def search(self, amendment_id: str, old: str | None, new: str, k: int = 5) -> Shortlist:
        """Shortlist the passages that share rare changed words with the amendment.

        `old` is None when the original text is unknown; then `new` is searched whole. Each
        distinct query term counts once, and term frequency saturates (BM25), so a passage
        cannot win by repeating one word. Raises ValueError for empty or over-long text.
        """
        kind: QueryKind
        if old is None:
            kind, query_text = "whole_text", TextChange(old="", new=new).new
        else:
            kind = "delta"
            query_text = " ".join(span.text for span in changed_spans(TextChange(old=old, new=new)))
        terms = tuple(sorted(set(_words(query_text))))
        scores = np.zeros(len(self._passages))
        for term in terms:
            if (span := self._spans.get(term)) is not None:
                start, stop = span
                # A term has one posting per passage, so the fancy-indexed add cannot collide.
                scores[self._indices[start:stop]] += self._weights[start:stop]
        # Every weight is positive, so exactly the passages sharing a term score above zero.
        matched = np.flatnonzero(scores)
        if 0 < k < matched.size:
            # Only passages tying or beating the k-th best score can win; sort just those.
            threshold = np.partition(scores[matched], -k)[-k]
            matched = matched[scores[matched] >= threshold]
        # Highest score first, then the earlier passage, as heapq.nlargest did.
        best: list[int] = matched[np.lexsort((matched, -scores[matched]))][: max(k, 0)].tolist()
        candidates = tuple(
            PassageCandidate(
                passage=self._passages[index],
                context_start=self._context(index)[0],
                context_end=self._context(index)[1],
                rank=rank,
                score=float(scores[index]),
                matched_terms=tuple(term for term in terms if term in self._terms[index]),
            )
            for rank, index in enumerate(best, start=1)
        )
        return Shortlist(
            amendment_id=amendment_id,
            query_kind=kind,
            query_terms=terms,
            candidates=candidates,
            limitations=_DELTA_LIMITATIONS if kind == "delta" else _WHOLE_TEXT_LIMITATIONS,
        )
