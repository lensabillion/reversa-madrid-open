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
# A quoted fragment starts and ends on a non-space and holds no quotation mark, so an
# apostrophe inside a fragment ends it early and the instruction is left unclassified.
_FRAGMENT = rf"[{_OPEN}](?P<{{name}}>[^{_QUOTES}\s](?:[^{_QUOTES}]*[^{_QUOTES}\s])?)[{_CLOSE}]"


def _fragment(name: str) -> str:
    return _FRAGMENT.format(name=name)


_INSTRUCTION = re.compile(
    rf"\b(?:(?P<replace>replace|change|substitute)\s+{_fragment('old')}"
    rf"\s+(?:with|by|to)\s+{_fragment('new')}"
    rf"|(?P<delete>delete|remove|strike)\s+{_fragment('gone')}"
    rf"|(?P<insert>insert|add)\s+{_fragment('added')})",
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
