"""Turn what a person types into one procedure, or into choices when it is unclear.

The jury names a law on the spot: "AI Act", "2021/0106(COD)", "32024R1689" or
"COM(2021) 206". Identifiers are recognised by shape and normalised; anything else is a
title search over the procedure catalog. A close title race returns the top candidates
instead of a guess, because analysing the wrong law looks exactly like analysing the
right one. No language model disambiguates (decision D1 is open).
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

type QueryKind = Literal["procedure", "celex", "com", "title"]

_PROCEDURE = re.compile(r"^(\d{4})\s*/\s*(\d{1,4})([A-Z]?)\s*\(?\s*([A-Za-z]{3})\s*\)?$")
_CELEX = re.compile(r"^(?:CELEX[:\s]*)?(\d{5}[A-Za-z]{1,2}\d{4})$", re.IGNORECASE)
_COM = re.compile(r"^COM\s*[(/]?\s*(\d{4})\s*[)/]?\s*/?\s*0*(\d{1,4})(?:\s*final)?$", re.IGNORECASE)
_PROPOSAL_CELEX = re.compile(r"^5(\d{4})PC0*(\d{1,4})$")
_WORD = re.compile(r"[^\W_]+")

# Words that appear in most procedure titles and so say nothing about which law is meant.
_FILLER = frozenset(
    {
        "a",
        "act",
        "and",
        "council",
        "directive",
        "eu",
        "european",
        "for",
        "in",
        "law",
        "of",
        "on",
        "parliament",
        "proposal",
        "regulation",
        "the",
        "to",
        "union",
    }
)
# A runner-up within this share of the best score makes the query ambiguous.
AMBIGUITY_MARGIN = 0.97
# Below this share of the query's words, a title is not a candidate at all.
MINIMUM_SCORE = 0.5
MAX_CHOICES = 3


@dataclass(frozen=True)
class LawQuery:
    kind: QueryKind
    # Normalised: `2021/0106(COD)`, `32024R1689`, `COM(2021)206`, or the trimmed text.
    value: str


def parse_query(text: str) -> LawQuery:
    """Recognise a procedure reference, CELEX number or COM reference; else a title."""
    trimmed = " ".join(text.split())
    if not trimmed:
        raise ValueError("The law query is empty")
    procedure = _PROCEDURE.match(trimmed)
    if procedure is not None:
        year, number, suffix, kind = procedure.groups()
        return LawQuery("procedure", f"{year}/{int(number):04d}{suffix}({kind.upper()})")
    celex = _CELEX.match(trimmed)
    if celex is not None:
        return LawQuery("celex", celex.group(1).upper())
    com = _COM.match(trimmed)
    if com is not None:
        return LawQuery("com", f"COM({com.group(1)}){int(com.group(2))}")
    return LawQuery("title", trimmed)


def com_reference_from_celex(celex: str) -> str | None:
    """`52021PC0206` is the proposal `COM(2021)206`; other CELEX sectors have no COM form."""
    match = _PROPOSAL_CELEX.match(celex)
    if match is None:
        return None
    return f"COM({match.group(1)}){int(match.group(2))}"


def title_tokens(title: str) -> frozenset[str]:
    """Lowercased words without filler; the whole word set when filler is all there is."""
    words = frozenset(word.lower() for word in _WORD.findall(title))
    return (words - _FILLER) or words


@dataclass(frozen=True)
class TitleCandidate:
    procedure_id: str
    title: str
    score: float
    # The alias that matched, when the match came from the alias table.
    alias: str | None = None


@dataclass(frozen=True)
class TitleResolution:
    """`chosen` is None when nothing matched or when the top candidates are too close."""

    chosen: TitleCandidate | None
    candidates: tuple[TitleCandidate, ...]

    @property
    def ambiguous(self) -> bool:
        return self.chosen is None and len(self.candidates) > 1


def _score(query: frozenset[str], title: frozenset[str]) -> float:
    """Share of the query's words the title holds, nudged towards shorter titles.

    The nudge (at most 0.1) only orders titles that hold the same query words: the
    regulation itself before a later act amending it, whose title is longer.
    """
    shared = len(query & title)
    if shared == 0:
        return 0.0
    return (shared / len(query)) * 0.9 + (shared / len(title)) * 0.1


def resolve_title(
    text: str,
    titles: Iterable[tuple[str, str]],
    aliases: Mapping[str, str] | None = None,
) -> TitleResolution:
    """Rank catalog titles against free text; an exact alias wins outright.

    `titles` yields (procedure_id, title). `aliases` maps a lowercased common name
    ("ai act") to a procedure id. Linear in the number of titles; the catalog holds a
    few thousand procedures.
    """
    query_key = " ".join(text.lower().split())
    known = dict(titles)
    alias_target = (aliases or {}).get(query_key)
    if alias_target is not None and alias_target in known:
        chosen = TitleCandidate(alias_target, known[alias_target], 1.0, alias=query_key)
        return TitleResolution(chosen, (chosen,))
    query = title_tokens(text)
    ranked = sorted(
        (
            TitleCandidate(procedure_id, title, score)
            for procedure_id, title in known.items()
            if (score := _score(query, title_tokens(title))) >= MINIMUM_SCORE
        ),
        key=lambda candidate: (-candidate.score, candidate.procedure_id),
    )[:MAX_CHOICES]
    if not ranked:
        return TitleResolution(None, ())
    if len(ranked) > 1 and ranked[1].score >= ranked[0].score * AMBIGUITY_MARGIN:
        return TitleResolution(None, tuple(ranked))
    return TitleResolution(ranked[0], tuple(ranked))
