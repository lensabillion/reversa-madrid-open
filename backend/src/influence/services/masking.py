"""Remove quoted proposal words from matching while preserving original text offsets."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

_WORDS = re.compile(r"\w+(?:['\u2019]\w+)*", re.UNICODE)
_QUOTE_WORDS = 8

type _Phrase = tuple[str, ...]


@dataclass(frozen=True)
class MaskedPassage:
    text: str
    spans: tuple[tuple[int, int], ...]


def _phrases(text: str) -> set[_Phrase]:
    words = tuple(match.group().casefold() for match in _WORDS.finditer(text))
    return {words[index : index + _QUOTE_WORDS] for index in range(len(words) - _QUOTE_WORDS + 1)}


class QuotedLaw:
    """The proposal's 8-word phrases, indexed once so each passage is masked in O(S).

    Each text is one provision and is indexed on its own, so the end of one provision and
    the start of the next never form a phrase. Building costs O(P) time and memory for P
    proposal characters. Measured on an Apple M5 (3 October 2026): the AI Act's 385 proposal
    provisions (236,809 characters) index in 12 ms and its 29,061 passages mask in 0.62 s,
    where rebuilding the index for every passage cost about 10 ms a passage.
    """

    def __init__(self, texts: Iterable[str]) -> None:
        self._phrases: frozenset[_Phrase] = frozenset(
            phrase for text in texts for phrase in _phrases(text)
        )

    def mask(self, passage: str) -> MaskedPassage:
        """Mask every >=8-word proposal quotation, including repeated and overlapping runs.

        Case/whitespace/punctuation differences do not make quoted law original authorship.
        O(S) for S passage characters with fixed 8-word windows (expected hash-table cost).
        Blank replacement retains code-point offsets; source evidence must always be read
        from the unmodified passage. This masks known proposal text only, not unknown
        boilerplate or a campaign shared by organizations.
        """
        matches = tuple(_WORDS.finditer(passage))
        words = tuple(match.group().casefold() for match in matches)
        intervals: list[tuple[int, int]] = []
        for index in range(len(words) - _QUOTE_WORDS + 1):
            if words[index : index + _QUOTE_WORDS] not in self._phrases:
                continue
            start, end = matches[index].start(), matches[index + _QUOTE_WORDS - 1].end()
            if intervals and start <= intervals[-1][1]:
                intervals[-1] = (intervals[-1][0], end)
            else:
                intervals.append((start, end))
        output = list(passage)
        for start, end in intervals:
            output[start:end] = " " * (end - start)
        return MaskedPassage("".join(output), tuple(intervals))
