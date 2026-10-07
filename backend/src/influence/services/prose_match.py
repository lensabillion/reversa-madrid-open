"""Case-folded words with exact Unicode offsets for lineage evidence."""

from dataclasses import dataclass
from re import Match

from influence.schemas.scoring import TOKEN_PATTERN


@dataclass(frozen=True, slots=True)
class Word:
    """A word of a text: its folded form and its half-open code-point offsets."""

    text: str
    start: int
    end: int


def words_of(text: str) -> tuple[Word, ...]:
    """The alphanumeric tokens of `text`, case-folded, with their offsets."""

    def folded(token: Match[str]) -> Word:
        return Word(token.group().casefold(), token.start(), token.end())

    return tuple(
        folded(token)
        for token in TOKEN_PATTERN.finditer(text)
        if any(char.isalnum() for char in token.group())
    )
