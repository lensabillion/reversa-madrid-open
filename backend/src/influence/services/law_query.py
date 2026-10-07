"""Turn what a person types into one procedure, or into choices when it is unclear.

The jury names a law on the spot: "AI Act", "2021/0106(COD)", "32024R1689" or
"COM(2021) 206". Identifiers are recognised by shape and normalised; anything else is
text, looked up first in the common-name table `LAW_ALIASES`, then as a title search over
the procedure catalog. A close title race returns the top candidates instead of a guess,
because analysing the wrong law looks exactly like analysing the right one. No language
model disambiguates (decision D1 is open).
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal
from unicodedata import combining, normalize

type QueryKind = Literal["procedure", "celex", "com", "title"]

_PROCEDURE = re.compile(r"^(\d{4})\s*/\s*(\d{1,4})([A-Z]?)\s*\(?\s*([A-Za-z]{3})\s*\)?$")
_CELEX = re.compile(r"^(?:CELEX[:\s]*)?(\d{5}[A-Za-z]{1,2}\d{4})$", re.IGNORECASE)
_COM = re.compile(r"^COM\s*[(/]?\s*(\d{4})\s*[)/]?\s*/?\s*0*(\d{1,4})(?:\s*final)?$", re.IGNORECASE)
_WORD = re.compile(r"[^\W_]+")
# Inside a name these join rather than separate: "A.I." is "AI", "Europe's" is "Europes".
_JOINERS = re.compile(r"[.'\N{RIGHT SINGLE QUOTATION MARK}]")
_ARTICLES = frozenset({"the", "a", "an"})

# Common names the title search cannot reach: an acronym ("DSA"), a name whose only
# distinctive word is not in the official title ("AI Act" against "Artificial
# Intelligence Act"), or a German, French or Spanish name, since the catalog's titles are
# English. A name maps to one procedure number and is compared by `name_key`, so case,
# accents, punctuation, spacing and a surrounding "the" never need their own entry. A
# wrong entry analyses the wrong law under a name the reader trusts, so a law nobody
# checked stays out; it still resolves by number, CELEX, COM reference or title.
LAW_ALIASES: Mapping[str, str] = {
    # PR #49's table. Each of these seven resolved to the right dossier in the real
    # Parltrack catalog on a laptop (3 October 2026).
    "ai act": "2021/0106(COD)",
    "aia": "2021/0106(COD)",
    "dsa": "2020/0361(COD)",
    "dma": "2020/0374(COD)",
    "csddd": "2022/0051(COD)",
    "cs3d": "2022/0051(COD)",
    "ehds": "2022/0140(COD)",
    # Added with branch feat/law-aliases. Each procedure number was checked on 3 October
    # 2026 against this repository's verified research tables or a public EUR-Lex or
    # Legislative Observatory page carrying it, not against the real catalog or CELLAR.
    "EU AI Act": "2021/0106(COD)",
    "KI-Verordnung": "2021/0106(COD)",
    "KI-Gesetz": "2021/0106(COD)",
    "Règlement sur l'intelligence artificielle": "2021/0106(COD)",
    "Règlement sur l'IA": "2021/0106(COD)",
    "Loi sur l'IA": "2021/0106(COD)",
    "Reglamento de Inteligencia Artificial": "2021/0106(COD)",
    "Reglamento de IA": "2021/0106(COD)",
    "Ley de IA": "2021/0106(COD)",
    "Digital Services Act": "2020/0361(COD)",
    "Gesetz über digitale Dienste": "2020/0361(COD)",
    "Règlement sur les services numériques": "2020/0361(COD)",
    "Reglamento de Servicios Digitales": "2020/0361(COD)",
    "Ley de Servicios Digitales": "2020/0361(COD)",
    "Digital Markets Act": "2020/0374(COD)",
    "Gesetz über digitale Märkte": "2020/0374(COD)",
    "Règlement sur les marchés numériques": "2020/0374(COD)",
    "Reglamento de Mercados Digitales": "2020/0374(COD)",
    "Ley de Mercados Digitales": "2020/0374(COD)",
    "Corporate Sustainability Due Diligence Directive": "2022/0051(COD)",
    # The plan's own example. Germany's national supply-chain act has the same name, but
    # it is not an EU procedure, so the catalog holds nothing else it could mean.
    "Lieferkettengesetz": "2022/0051(COD)",
    "EU-Lieferkettengesetz": "2022/0051(COD)",
    "EU-Lieferkettenrichtlinie": "2022/0051(COD)",
    "European Health Data Space": "2022/0140(COD)",
    "Data Act": "2022/0047(COD)",
    "EU Data Act": "2022/0047(COD)",
    # Proposed in 2012, before the Atlas's 2019 scope; listed because it is the law a jury
    # is most likely to name and LobbyPlag's practice labels come from it.
    "GDPR": "2012/0011(COD)",
    "General Data Protection Regulation": "2012/0011(COD)",
    "DSGVO": "2012/0011(COD)",
    "Datenschutz-Grundverordnung": "2012/0011(COD)",
    "Datenschutzgrundverordnung": "2012/0011(COD)",
    "RGPD": "2012/0011(COD)",
    "MiCA": "2020/0265(COD)",
    "MiCAR": "2020/0265(COD)",
    "Markets in Crypto-Assets Regulation": "2020/0265(COD)",
    "DORA": "2020/0266(COD)",
    "Digital Operational Resilience Act": "2020/0266(COD)",
    "Minimum Wage Directive": "2020/0310(COD)",
    "Adequate Minimum Wages Directive": "2020/0310(COD)",
    "DGA": "2020/0340(COD)",
    "Data Governance Act": "2020/0340(COD)",
    "Batteries Regulation": "2020/0353(COD)",
    "Battery Regulation": "2020/0353(COD)",
    "NIS2": "2020/0359(COD)",
    "NIS 2": "2020/0359(COD)",
    "NIS2 Directive": "2020/0359(COD)",
    "Pay Transparency Directive": "2021/0050(COD)",
    "CSRD": "2021/0104(COD)",
    "Corporate Sustainability Reporting Directive": "2021/0104(COD)",
    "eIDAS 2": "2021/0136(COD)",
    "eIDAS2": "2021/0136(COD)",
    "eIDAS 2.0": "2021/0136(COD)",
    "European Digital Identity Regulation": "2021/0136(COD)",
    "CBAM": "2021/0214(COD)",
    "Carbon Border Adjustment Mechanism": "2021/0214(COD)",
    "EUDR": "2021/0366(COD)",
    "Deforestation Regulation": "2021/0366(COD)",
    "EU Deforestation Regulation": "2021/0366(COD)",
    "Platform Work Directive": "2021/0414(COD)",
    "Chips Act": "2022/0032(COD)",
    "European Chips Act": "2022/0032(COD)",
    "EU Chips Act": "2022/0032(COD)",
    "ESPR": "2022/0095(COD)",
    "Ecodesign for Sustainable Products Regulation": "2022/0095(COD)",
    "Nature Restoration Law": "2022/0195(COD)",
    # Not "CRA": in financial law that is the credit rating agencies regulation.
    "Cyber Resilience Act": "2022/0272(COD)",
    "EMFA": "2022/0277(COD)",
    "European Media Freedom Act": "2022/0277(COD)",
    "Media Freedom Act": "2022/0277(COD)",
    "Euro 7": "2022/0365(COD)",
    "PPWR": "2022/0396(COD)",
    "Packaging and Packaging Waste Regulation": "2022/0396(COD)",
    "Packaging Regulation": "2022/0396(COD)",
    "CRMA": "2023/0079(COD)",
    "Critical Raw Materials Act": "2023/0079(COD)",
    "NZIA": "2023/0081(COD)",
    "Net-Zero Industry Act": "2023/0081(COD)",
}

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


def title_tokens(title: str) -> frozenset[str]:
    """Lowercased words without filler; the whole word set when filler is all there is."""
    words = frozenset(word.lower() for word in _WORD.findall(title))
    return (words - _FILLER) or words


def name_key(name: str) -> str:
    """The form in which two spellings of one name are equal: "The A.I.-Act" is `ai act`.

    Case, accents, spacing and punctuation are dropped, and so are English articles at
    either end, so "Reglement sur l'IA" typed without its accent still matches. Unlike
    `title_tokens` it keeps word order and filler, so it says whether two names are the
    same name, not whether they share a topic.
    """
    # Unicode's compatibility caseless form (definition D146), then accents removed. The
    # per-character pass is skipped for ASCII, which most catalog titles are: it is most
    # of the cost of comparing a name with all 24,000 titles.
    folded = normalize("NFKD", normalize("NFKD", normalize("NFD", name).casefold()).casefold())
    if not folded.isascii():
        folded = "".join(character for character in folded if not combining(character))
    words = _WORD.findall(_JOINERS.sub("", folded))
    while words and words[0] in _ARTICLES:
        words.pop(0)
    while words and words[-1] in _ARTICLES:
        words.pop()
    return " ".join(words)


@dataclass(frozen=True)
class TitleCandidate:
    procedure_id: str
    title: str
    score: float
    # The alias that matched, as the table spells it, when the match came from the table.
    alias: str | None = None


@dataclass(frozen=True)
class TitleResolution:
    """`chosen` is None when nothing matched or when the top candidates are too close.

    `missing` is the procedure an alias names when `titles` does not hold it. The text
    then resolves to nothing rather than to a title: the name was meant for that law.
    """

    chosen: TitleCandidate | None
    candidates: tuple[TitleCandidate, ...]
    missing: str | None = None

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


def _by_alias(
    text: str, known: Mapping[str, str], aliases: Mapping[str, str]
) -> TitleResolution | None:
    """The procedure a common name stands for; None when `text` is no name in `aliases`.

    Only an equally exact name can contradict it: another alias spelt the same way by
    `name_key` but naming another procedure, or a title that is the name itself. Either
    returns the choices. A title that merely shares a word does not: "AI Act" shares "AI"
    with titles of other AI files, which the title search would pick.
    """
    key = name_key(text)
    named = {procedure: name for name, procedure in aliases.items() if name_key(name) == key}
    if not named:
        return None
    titled = {procedure for procedure, title in known.items() if name_key(title) == key}
    found = sorted({*named, *titled})
    if len(found) > 1:
        choices = (TitleCandidate(p, known.get(p, p), 1.0, named.get(p)) for p in found)
        return TitleResolution(None, tuple(choices))
    (procedure,) = found
    if procedure not in known:
        return TitleResolution(None, (), missing=procedure)
    chosen = TitleCandidate(procedure, known[procedure], 1.0, named[procedure])
    return TitleResolution(chosen, (chosen,))


def resolve_title(
    text: str,
    titles: Iterable[tuple[str, str]],
    aliases: Mapping[str, str] | None = None,
) -> TitleResolution:
    """Rank catalog titles against free text; a common name in `aliases` comes first.

    `titles` yields (procedure_id, title). `aliases` maps a common name ("AI Act") to a
    procedure id; names compare by `name_key`. Linear in the number of titles and
    aliases; the catalog holds about 24,000 procedures and the table about a hundred names.
    """
    known = dict(titles)
    if aliases:
        by_alias = _by_alias(text, known, aliases)
        if by_alias is not None:
            return by_alias
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
