"""Cut a submission into short overlapping passages with exact offsets into its text.

A passage is a unit of consultation wording searched and quoted by lineage, so its offsets
must index the unmodified document text: `text[start:end] == passage.text`, always. The
splitter therefore never rewrites, joins or normalises anything; it only chooses cut
points. Sentence detection is a small rule set, not a model: it has to survive PDF text
(hard line wraps, bullets, page numbers) and legal prose ("Art. 5", "No. 3", "e.g.").
"""

import re
from collections.abc import Iterator
from datetime import datetime
from typing import NamedTuple

from influence.schemas.atlas import DocumentText, Passage, SourceDocument, SourceSpan, id_part

DEFAULT_MAX_SENTENCES = 3
DEFAULT_OVERLAP = 1
# About 120 words is the longest passage a reader checks at a glance; a "sentence" longer
# than this (a table, an unpunctuated list) is cut at word boundaries.
DEFAULT_MAX_WORDS = 120

_BULLET = (
    r"[ \t]*(?:[-*\u2022\u00b7\u2013\u2014\u25aa\u25e6\u25cf\u25cb\uf0b7]"
    r"|\(?(?:\d{1,3}|[A-Za-z])[.)])[ \t]"
)
# Three kinds of cut: sentence punctuation followed by white space, a blank line, and a
# line break before a bullet. A single line break is only PDF wrapping and never cuts.
_CUT = re.compile(
    r"(?P<stop>[.!?\u2026]+[\"')\]\u00bb\u201d\u2019]*)(?=\s)"
    r"|(?P<blank>\n[ \t\r\f\v]*\n)"
    rf"|(?P<bullet>\n(?={_BULLET}))"
)
_ABBREVIATIONS: frozenset[str] = frozenset(
    {
        "abs", "al", "approx", "art", "arts", "bzw", "ca", "cf", "ch", "co", "corp", "dr",
        "ed", "eds", "excl", "fig", "figs", "inc", "incl", "ltd", "mr", "mrs", "ms", "no",
        "nos", "nr", "p", "para", "paras", "pp", "prof", "rec", "ref", "reg", "resp", "sec",
        "st", "viz", "vol", "vs",
    }
)  # fmt: skip
_OPENERS = "\"'([\u00ab\u201c\u2018"
_PAGE_NUMBER = re.compile(
    r"(?:page|seite|p\.?|pag\.?|pagina|p\u00e1gina)?\s*\d{1,4}"
    r"(?:\s*(?:/|of|von|de|sur|di)\s*\d{1,4})?",
    re.IGNORECASE,
)
_WORD = re.compile(r"\S+")


class PassageError(ValueError):
    """The splitter was asked for something that cannot yield valid passages."""


class TextSpan(NamedTuple):
    """Half-open Unicode code-point offsets into the text that was split, and the slice."""

    start: int
    end: int
    text: str


def _is_abbreviation(text: str, stop: int) -> bool:
    """True when the full stop at `stop` closes an abbreviation, initial or list number.

    Scans back only to the previous white space, so the whole split stays linear.
    """
    begin = stop
    while begin > 0 and not text[begin - 1].isspace():
        begin -= 1
    token = text[begin:stop].lstrip(_OPENERS).lower()
    if token in _ABBREVIATIONS:
        return True
    if len(token) == 1 and token.isalpha():
        return True
    parts = token.split(".")
    if len(parts) > 1 and all(part.isalpha() and len(part) <= 2 for part in parts):
        # "e.g", "i.e", "U.S", "z.B": short dotted groups.
        return True
    if token.isdigit():
        # "1." opening a line is a list number; "in 2021." ends a sentence.
        before = begin
        while before > 0 and text[before - 1] in " \t":
            before -= 1
        return before == 0 or text[before - 1] == "\n"
    return False


def _continues(text: str, position: int) -> bool:
    """True when the next visible character is lower case: the sentence goes on."""
    while position < len(text) and text[position].isspace():
        position += 1
    return position < len(text) and text[position].islower()


def _cuts(text: str) -> Iterator[int]:
    for match in _CUT.finditer(text):
        stop = match.group("stop")
        if stop is None:
            yield match.start()
        elif stop[0] in "!?":
            yield match.end()
        elif stop.startswith("."):
            if not (
                (stop == "." and _is_abbreviation(text, match.start()))
                or _continues(text, match.end())
            ):
                yield match.end()
        elif not _continues(text, match.end()):
            yield match.end()


def _is_noise(sentence: str) -> bool:
    """Page numbers, rules and stray bullets carry no ask and only pollute retrieval."""
    return _PAGE_NUMBER.fullmatch(sentence) is not None or not any(
        character.isalpha() for character in sentence
    )


def _bounded(text: str, start: int, end: int, max_words: int) -> Iterator[tuple[int, int, int]]:
    """Yield `(start, end, words)`, cutting an over-long sentence at word boundaries."""
    words = [
        (start + match.start(), start + match.end()) for match in _WORD.finditer(text[start:end])
    ]
    for first in range(0, len(words), max_words):
        chunk = words[first : first + max_words]
        yield chunk[0][0], chunk[-1][1], len(chunk)


def split_sentences(
    text: str, *, max_words: int = DEFAULT_MAX_WORDS
) -> tuple[tuple[int, int, int], ...]:
    """Sentences as `(start, end, word_count)`, white space trimmed, noise removed."""
    sentences: list[tuple[int, int, int]] = []
    previous = 0
    for cut in (*_cuts(text), len(text)):
        segment = text[previous:cut]
        stripped = segment.strip()
        if stripped and not _is_noise(stripped):
            start = previous + len(segment) - len(segment.lstrip())
            sentences.extend(_bounded(text, start, start + len(stripped), max_words))
        previous = cut
    return tuple(sentences)


def split_passages(
    text: str,
    *,
    max_sentences: int = DEFAULT_MAX_SENTENCES,
    overlap: int = DEFAULT_OVERLAP,
    max_words: int = DEFAULT_MAX_WORDS,
) -> tuple[TextSpan, ...]:
    """Windows of up to `max_sentences` sentences and `max_words` words, sharing `overlap`.

    A window always holds at least one sentence and always advances by at least one, and
    the last window is the one that reaches the end of the text, so no passage is a
    strict subset of the one before it. Linear in the length of the text.
    """
    if max_sentences < 1 or max_words < 1 or not 0 <= overlap < max_sentences:
        raise PassageError(
            "Need max_sentences >= 1, max_words >= 1 and 0 <= overlap < max_sentences"
        )
    sentences = split_sentences(text, max_words=max_words)
    passages: list[TextSpan] = []
    first = 0
    while first < len(sentences):
        last = first
        words = sentences[first][2]
        while (
            last + 1 < len(sentences)
            and last + 1 - first < max_sentences
            and words + sentences[last + 1][2] <= max_words
        ):
            last += 1
            words += sentences[last][2]
        start, end = sentences[first][0], sentences[last][1]
        # A window that cannot grow past the one before it (the next sentence would break
        # the word limit) lies inside it, and repeating it would duplicate evidence.
        if not passages or end > passages[-1].end:
            passages.append(TextSpan(start, end, text[start:end]))
        if last + 1 == len(sentences):
            break
        first += max(1, last + 1 - first - overlap)
    return tuple(passages)


def document_passages(
    document: SourceDocument,
    text: DocumentText,
    *,
    procedure_id: str,
    actor_id: str,
    submitted_at: datetime | None,
) -> tuple[Passage, ...]:
    """Collection passages for one document; the actor comes from the caller's resolver.

    The language is whatever the source declared for the document (Have Your Say's
    `language` for feedback text, nothing for attachments): it is not detected here.
    """
    if document.document_id != text.document_id:
        raise PassageError(
            f"Text of {text.document_id} does not belong to document {document.document_id}"
        )
    prefix = f"passage:{id_part(document.document_id)}"
    return tuple(
        Passage(
            passage_id=f"{prefix}:{number}",
            procedure_id=procedure_id,
            document_id=document.document_id,
            actor_id=actor_id,
            span=SourceSpan(
                record_id=document.document_id,
                field="text",
                start=span.start,
                end=span.end,
                text=span.text,
            ),
            submitted_at=submitted_at,
            language=document.language,
        )
        for number, span in enumerate(split_passages(text.text), start=1)
    )
