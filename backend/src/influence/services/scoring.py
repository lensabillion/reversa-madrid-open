"""Bounded token differences for lineage's candidate queries and quoted instructions."""

from difflib import SequenceMatcher
from re import Match

from influence.schemas.scoring import TOKEN_PATTERN, ChangeSpan, Operation, TextChange


def changed_spans(change: TextChange) -> tuple[ChangeSpan, ...]:
    """Token diff is worst-case O(n*m), bounded to 800 tokens per side at validation."""
    old = tuple(TOKEN_PATTERN.finditer(change.old))
    new = tuple(TOKEN_PATTERN.finditer(change.new))
    matcher = SequenceMatcher(
        None,
        tuple(token.group().casefold() for token in old),
        tuple(token.group().casefold() for token in new),
        autojunk=False,
    )
    spans: list[ChangeSpan] = []
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        edits: tuple[tuple[Operation, tuple[Match[str], ...], int, int, str], ...] = (
            ("delete", old, old_start, old_end, change.old),
            ("insert", new, new_start, new_end, change.new),
        )
        for operation, tokens, start, end, text in edits:
            if start < end:
                left, right = tokens[start].start(), tokens[end - 1].end()
                spans.append(
                    ChangeSpan(operation=operation, start=left, end=right, text=text[left:right])
                )
    return tuple(spans)
