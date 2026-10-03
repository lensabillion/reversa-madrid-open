"""Part 3, find candidates: a per-law BM25 index over submission passages.

Retrieval only narrows the search. A high score means shared rare words, not influence.
"""

import re
from collections import Counter, defaultdict
from heapq import nlargest
from math import log

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

    Build is linear in total tokens. A query costs the postings of its distinct terms plus
    O(M log k) to keep the top k of M matching passages.
    """

    def __init__(self, passages: tuple[SourcePassage, ...]) -> None:
        self._passages = passages
        self._lengths: list[int] = []
        self._postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for index, passage in enumerate(passages):
            counts = Counter(_words(passage.text))
            self._lengths.append(sum(counts.values()))
            for term, count in counts.items():
                self._postings[term].append((index, count))
        self._average_length = sum(self._lengths) / len(passages) if passages else 0.0

    def __len__(self) -> int:
        return len(self._passages)

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
        scores: dict[int, float] = defaultdict(float)
        matched: dict[int, list[str]] = defaultdict(list)
        total = len(self._passages)
        for term in terms:
            postings = self._postings.get(term, ())
            idf = log(1 + (total - len(postings) + 0.5) / (len(postings) + 0.5))
            for index, count in postings:
                norm = 1 - _B + _B * self._lengths[index] / self._average_length
                scores[index] += idf * count * (_K1 + 1) / (count + _K1 * norm)
                matched[index].append(term)
        best = nlargest(k, scores.items(), key=lambda item: (item[1], -item[0]))
        candidates = tuple(
            PassageCandidate(
                passage=self._passages[index],
                context_start=self._context(index)[0],
                context_end=self._context(index)[1],
                rank=rank,
                score=score,
                matched_terms=tuple(matched[index]),
            )
            for rank, (index, score) in enumerate(best, start=1)
        )
        return Shortlist(
            amendment_id=amendment_id,
            query_kind=kind,
            query_terms=terms,
            candidates=candidates,
            limitations=_DELTA_LIMITATIONS if kind == "delta" else _WHOLE_TEXT_LIMITATIONS,
        )
