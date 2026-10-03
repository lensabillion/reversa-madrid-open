"""Part 3 to part 4 bridge: read which change a submission passage asks for.

The scorer compares changes, not paragraphs. A submission passage such as "In Article 9(2),
replace 'shall' with 'may': ..." asks for one change; handing the scorer the whole
paragraph as an insertion buries that change in unrelated words. This reader pulls out the
requests that are spelled as quoted instructions and leaves everything else as an
unclassified statement. It never guesses the original wording or the legal direction.
Linear in the passage length.
"""

import re

from influence.schemas.retrieval import PassageChange

_OPEN = "\"'\N{LEFT SINGLE QUOTATION MARK}\N{LEFT DOUBLE QUOTATION MARK}"
_CLOSE = "\"'\N{RIGHT SINGLE QUOTATION MARK}\N{RIGHT DOUBLE QUOTATION MARK}"
_QUOTES = _OPEN + _CLOSE
# A quoted fragment starts and ends on a non-space and holds no quotation mark. Its closing
# mark must not be followed by a letter: in "the provider's obligation" the apostrophe is not
# a closing quote, and reading 'the provider' as the whole fragment would invent an
# instruction. Such a passage is left unclassified rather than cut short.
_FRAGMENT = (
    rf"[{_OPEN}](?P<{{name}}>[^{_QUOTES}\s](?:[^{_QUOTES}]*[^{_QUOTES}\s])?)[{_CLOSE}]"
    r"(?![^\W\d_])"
)


def _fragment(name: str) -> str:
    return _FRAGMENT.format(name=name)


_INSTRUCTION = re.compile(
    rf"\b(?:(?P<replace>replace|change|substitute)\s+{_fragment('old')}"
    rf"\s+(?:with|by|to)\s+{_fragment('new')}"
    rf"|(?P<delete>delete|remove|strike)\s+{_fragment('gone')}"
    rf"|(?P<insert>insert|add)\s+{_fragment('added')})",
    re.IGNORECASE,
)
# A sentence ends at . ! ? or ; followed by a space or a line feed, or at a line feed.
_SENTENCE_END = re.compile("[.!?;][ \N{LINE FEED}]|\N{LINE FEED}")
# Words that turn an instruction into its opposite when they precede it in the same sentence:
# "we oppose any proposal to insert 'X'", "please do not delete 'X'". The list is
# deliberately broad; a false hit only withholds publication, a miss publishes a reversal.
_OPPOSITION = re.compile(
    r"\b(?:not|no|never|cannot|\w+n['\N{RIGHT SINGLE QUOTATION MARK}]t|oppos\w*|reject\w*"
    r"|against|object(?:s|ed|ing)?\s+to|objection|avoid\w*|refrain\w*)\b",
    re.IGNORECASE,
)


def read_changes(passage: str) -> tuple[PassageChange, ...]:
    """Return the quoted instructions in `passage` in order, or the passage as a statement.

    Recognised: replace/change/substitute 'X' with/by/to 'Y'; delete/remove/strike 'X';
    insert/add 'X'. A passage with none of them comes back as one "statement" whose `old`
    is None, because the original wording is unknown, not empty. A blank passage has no
    change.
    """
    changes: list[PassageChange] = []
    for match in _INSTRUCTION.finditer(passage):
        if match["replace"]:
            kind, old, new = "replace", match["old"], match["new"]
        elif match["delete"]:
            kind, old, new = "delete", match["gone"], ""
        else:
            kind, old, new = "insert", "", match["added"]
        changes.append(
            PassageChange(
                kind=kind,
                old=old,
                new=new,
                start=match.start(),
                end=match.end(),
                text=match.group(),
            )
        )
    if changes:
        return tuple(changes)
    stripped = passage.strip()
    if not stripped:
        return ()
    start = passage.index(stripped)
    return (
        PassageChange(
            kind="statement",
            old=None,
            new=stripped,
            start=start,
            end=start + len(stripped),
            text=stripped,
        ),
    )


def opposed_sentence(passage: str, change: PassageChange) -> tuple[int, int] | None:
    """The sentence holding `change`, when an opposition cue precedes the instruction in it.

    Returns the sentence's half-open offsets in `passage` (trimmed of surrounding blanks) so
    a caller can quote the whole sentence, "do not" included, or None when no cue precedes.
    A statement is never an instruction, so it has no opposition to read. Linear in the
    passage length.
    """
    if change.kind == "statement":
        return None
    start = max((end.end() for end in _SENTENCE_END.finditer(passage, 0, change.start)), default=0)
    if not _OPPOSITION.search(passage, start, change.start):
        return None
    ender = _SENTENCE_END.search(passage, change.end)
    end = len(passage) if ender is None else ender.start() + 1
    sentence = passage[start:end]
    stripped = sentence.strip()
    first = start + sentence.index(stripped)
    return first, first + len(stripped)
