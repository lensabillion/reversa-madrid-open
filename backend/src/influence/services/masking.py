"""Remove quoted proposal words from matching while preserving original text offsets."""

import re
from dataclasses import dataclass

_WORDS = re.compile(r"\w+(?:['\u2019]\w+)*", re.UNICODE)
_QUOTE_WORDS = 8


@dataclass(frozen=True)
class MaskedPassage:
    text: str
    spans: tuple[tuple[int, int], ...]


def mask_quoted_law(passage: str, proposal: str) -> MaskedPassage:
    """Mask every >=8-word proposal quotation, including repeated and overlapping runs.

    Case/whitespace/punctuation differences do not make quoted law original authorship.
    O(P + S) time and memory for P proposal and S passage characters with fixed 8-word
    windows (expected hash-table cost). Blank replacement retains code-point offsets;
    source evidence must always be read from the unmodified passage. This masks known
    proposal text only, not unknown boilerplate or a campaign shared by organizations.
    """
    proposal_words = tuple(match.group().casefold() for match in _WORDS.finditer(proposal))
    phrases = {
        proposal_words[index : index + _QUOTE_WORDS]
        for index in range(len(proposal_words) - _QUOTE_WORDS + 1)
    }
    matches = tuple(_WORDS.finditer(passage))
    words = tuple(match.group().casefold() for match in matches)
    intervals: list[tuple[int, int]] = []
    for index in range(len(words) - _QUOTE_WORDS + 1):
        if words[index : index + _QUOTE_WORDS] not in phrases:
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
