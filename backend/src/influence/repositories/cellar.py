"""CELLAR, the EU Publications Office repository: a law's identifiers and its texts.

Two services are used. The SPARQL endpoint maps a procedure to the CELEX numbers of its
proposal and final act (and back). Content negotiation on a CELEX URI returns the act as
XHTML, which is split here into recitals, articles and numbered paragraphs.

The EUR-Lex website is never used: it answers scripts with a bot challenge.

Two markups exist and they share nothing. Official Journal acts carry ELI subdivision ids
(`rct_12`, `art_5`, `anx_I`), which are language independent. Commission proposals are a
Word export with no ids, so their structure is read from the English text itself
("Whereas:", "Article 5"). A document that fits neither yields its text and no provisions,
with the reason: an invented provision would be quoted as law.

A proposal's annexes are separate streams of the same CELLAR item, so they are fetched with
the act and split at their "ANNEX I" headings into the same one-provision-per-annex shape the
Official Journal gives a final act. Without them, wording that the final act's annexes kept
from the proposal would look new.
"""

import hashlib
import re
import urllib.parse
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Literal, NamedTuple

from pydantic import BaseModel, ValidationError

from influence.extraction.fetching import CachedFetcher, FetchError
from influence.schemas.atlas import (
    ArticleStage,
    ArticleVersion,
    DocumentText,
    ExtractionStatus,
    ProvisionKind,
    SourceDocument,
    document_id,
    id_part,
)
from influence.schemas.scoring import FrozenModel

SPARQL_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
RESOURCE_BASE = "http://publications.europa.eu/resource"
SPARQL_ACCEPT = "application/sparql-results+json"
ACT_ACCEPT = "application/xhtml+xml, text/html;q=0.9"
REUSE_TERMS = "Commission reuse policy, CC BY 4.0 (Decision 2011/833/EU)"
EXTRACTION_METHOD = "cellar-xhtml-v1"
HTTP_NOT_FOUND = 404
HTTP_MULTIPLE_CHOICES = 300

_PREFIXES = (
    "PREFIX cdm: <http://publications.europa.eu/ontology/cdm#> "
    "PREFIX owl: <http://www.w3.org/2002/07/owl#> "
)
_PROCEDURE = re.compile(r"(\d{4})/(\d{4})[A-Z]?\(([A-Z]{3})\)")
_CELLAR_REFERENCE = re.compile(r"(\d{4})/(\d{4})/([A-Z]{3})")
# Checked before a CELEX is placed in a query or a URL: nothing else may reach either.
_CELEX = re.compile(r"[0-9A-Z()]{6,24}")
_COM_PROPOSAL = re.compile(r"5(\d{4})PC(\d{4})")
_CORRIGENDUM = re.compile(r"R\(\d+\)$")
_PARLIAMENT_POSITION = re.compile(r"5\d{4}AP\d{4}")
_STREAM = re.compile(
    r'<a href="([^"]+)".*?title="stream_name">([^<]*)<.*?title="stream_order"[^>]*>(\d+)<',
    re.DOTALL,
)


class CellarError(RuntimeError):
    """CELLAR was asked something it cannot answer, or answered something unreadable."""


# --- Identifiers ------------------------------------------------------------------------


class LawIdentifiers(FrozenModel):
    """What CELLAR knows a procedure by. An identifier is set only when it is the only one.

    A dossier can produce several acts (a package adopted under one procedure number).
    Choosing one would silently drop the others, so `celex_final` stays None, every
    candidate is listed and `ambiguous` is True. Corrigenda (`...R(01)`) are listed as
    candidates but are not rivals of the act they correct.
    """

    procedure_id: str
    celex_proposal: str | None
    celex_final: str | None
    com_reference: str | None
    proposal_candidates: tuple[str, ...] = ()
    final_candidates: tuple[str, ...] = ()
    ambiguous: bool = False


class _Cell(BaseModel):
    value: str


class _Results(BaseModel):
    bindings: list[dict[str, _Cell]]


class _SparqlResponse(BaseModel):
    results: _Results


def procedure_uri(procedure_id: str) -> str:
    """`2021/0106(COD)` is `procedure/2021_106` in CELLAR: no padding, no procedure type."""
    match = _PROCEDURE.fullmatch(procedure_id)
    if match is None:
        raise CellarError(f"Not a procedure reference: {procedure_id!r}")
    return f"{RESOURCE_BASE}/procedure/{match[1]}_{int(match[2])}"


def com_reference(celex: str | None) -> str | None:
    """`52021PC0206` is `COM(2021)206`. Any other document type has no COM number."""
    match = _COM_PROPOSAL.fullmatch(celex or "")
    return None if match is None else f"COM({match[1]}){int(match[2])}"


def _select(fetcher: CachedFetcher, query: str, *, refresh: bool) -> list[dict[str, str]]:
    url = f"{SPARQL_ENDPOINT}?{urllib.parse.urlencode({'query': query})}"
    try:
        response = fetcher.get(url, refresh=refresh, headers={"Accept": SPARQL_ACCEPT})
    except FetchError as error:
        raise CellarError(f"CELLAR SPARQL request failed: {error.reason}") from error
    try:
        parsed = _SparqlResponse.model_validate_json(response.body)
    except ValidationError as error:
        raise CellarError("CELLAR SPARQL answer is not a SELECT result in JSON") from error
    return [{name: cell.value for name, cell in row.items()} for row in parsed.results.bindings]


def _distinct(rows: Iterable[dict[str, str]], name: str) -> tuple[str, ...]:
    return tuple(sorted({row[name] for row in rows if name in row}))


def _only(candidates: Sequence[str]) -> str | None:
    return candidates[0] if len(candidates) == 1 else None


def resolve_celex(
    fetcher: CachedFetcher, procedure_id: str, *, refresh: bool = False
) -> LawIdentifiers:
    """Map a procedure to its proposal and final act. No rows means None, not an error.

    An ongoing procedure has a proposal and no final act; a procedure CELLAR does not
    know has neither. Pass `refresh=True` for an ongoing procedure, whose cached answer
    goes stale the day the act is published.
    """
    query = (
        f"{_PREFIXES}SELECT ?final ?prop WHERE {{ "
        f"?d owl:sameAs <{procedure_uri(procedure_id)}> . "
        "OPTIONAL { ?d cdm:dossier_produces_resource_legal ?w . "
        "?w cdm:resource_legal_id_celex ?final . } "
        "OPTIONAL { ?d cdm:dossier_initiated_by_act_preparatory ?p . "
        "?p cdm:resource_legal_id_celex ?prop . } }"
    )
    rows = _select(fetcher, query, refresh=refresh)
    finals = _distinct(rows, "final")
    proposals = _distinct(rows, "prop")
    acts = [celex for celex in finals if _CORRIGENDUM.search(celex) is None]
    proposal = _only(proposals)
    return LawIdentifiers(
        procedure_id=procedure_id,
        celex_proposal=proposal,
        celex_final=_only(acts),
        com_reference=com_reference(proposal),
        proposal_candidates=proposals,
        final_candidates=finals,
        ambiguous=len(acts) > 1 or len(proposals) > 1,
    )


def _checked_celex(celex: str) -> str:
    if _CELEX.fullmatch(celex) is None:
        raise CellarError(f"Not a CELEX number: {celex!r}")
    return celex


def procedures_for_celex(
    fetcher: CachedFetcher, celex: str, *, refresh: bool = False
) -> tuple[str, ...]:
    """Every procedure whose dossier contains this document, as `2021/0106(COD)`.

    CELLAR stores the interinstitutional reference with its type (`2021/0106/COD`), so
    the full reference comes back. A reference in another shape is dropped, not repaired.
    """
    query = (
        f"{_PREFIXES}SELECT DISTINCT ?ref WHERE {{ "
        f'?w cdm:resource_legal_id_celex ?c . FILTER(STR(?c) = "{_checked_celex(celex)}") '
        "?d ?relation ?w . "
        "?d cdm:procedure_code_interinstitutional_reference_procedure ?ref . }"
    )
    matches = (
        _CELLAR_REFERENCE.fullmatch(reference)
        for reference in _distinct(_select(fetcher, query, refresh=refresh), "ref")
    )
    return tuple(f"{match[1]}/{match[2]}({match[3]})" for match in matches if match is not None)


def procedure_for_celex(fetcher: CachedFetcher, celex: str, *, refresh: bool = False) -> str | None:
    """The one procedure behind a CELEX, or None when there is none or more than one.

    Several procedures is a real case (an act amended by later procedures can sit in
    more than one dossier); `procedures_for_celex` lists them for the caller to choose.
    """
    return _only(procedures_for_celex(fetcher, celex, refresh=refresh))


def resolve_position_celex(
    fetcher: CachedFetcher, procedure_id: str, *, refresh: bool = False
) -> tuple[str, ...]:
    """CELEX numbers of Parliament's adopted texts (`5YYYYAPNNNN`) filed in the dossier.

    The dossier lists what was filed, which for the AI Act is the first-reading
    resolution of March 2024 and not the June 2023 amendments, so the result is every
    candidate and may be empty.
    """
    query = (
        f"{_PREFIXES}SELECT DISTINCT ?celex WHERE {{ "
        f"?d owl:sameAs <{procedure_uri(procedure_id)}> . "
        "?d cdm:dossier_contains_work ?w . ?w cdm:resource_legal_id_celex ?celex . }"
    )
    contained = _distinct(_select(fetcher, query, refresh=refresh), "celex")
    return tuple(celex for celex in contained if _PARLIAMENT_POSITION.fullmatch(celex))


# --- Fetching an act --------------------------------------------------------------------


@dataclass(frozen=True)
class FetchedAct:
    """The bytes of one act and what is needed to cite them."""

    celex: str
    # The address the bytes came from: the CELEX URI, or the stream chosen from a list.
    url: str
    language: str
    retrieved_at: datetime
    sha256: str
    media_type: str | None
    body: bytes = field(repr=False)
    # The proposal's annex streams, in order; a final act has none (its annexes are inline).
    annexes: tuple[bytes, ...] = field(default=(), repr=False)
    # One "<url>: <reason>" per annex stream that was listed and could not be fetched.
    annex_gaps: tuple[str, ...] = ()


@dataclass(frozen=True)
class MissingAct:
    """Why there is no text: `missing` is CELLAR saying so, `failed` is a broken request."""

    celex: str
    url: str
    language: str
    status: Literal["missing", "failed"]
    reason: str
    http_status: int | None = None


def celex_url(celex: str) -> str:
    return f"{RESOURCE_BASE}/celex/{_checked_celex(celex)}"


def act_stream_url(listing: bytes) -> str | None:
    """Pick the act out of a 300 Multiple Choices list: the first stream that is no annex.

    A proposal is stored as several streams (`1_EN_ACT_part1_v7.html`,
    `2_EN_annexe_proposition_part1_v7.html`). Their labels vary between proposals, so
    the stream name and order decide.
    """
    streams = [
        (int(order), href)
        for href, name, order in _STREAM.findall(listing.decode("utf-8", errors="replace"))
        if "annex" not in name.lower()
    ]
    return min(streams)[1] if streams else None


def annex_stream_urls(listing: bytes) -> tuple[str, ...]:
    """The annex streams of a 300 Multiple Choices list, in their stream order."""
    streams = [
        (int(order), href)
        for href, name, order in _STREAM.findall(listing.decode("utf-8", errors="replace"))
        if "annex" in name.lower()
    ]
    return tuple(href for _, href in sorted(streams))


def fetch_act(
    fetcher: CachedFetcher, celex: str, *, language: str = "eng", refresh: bool = False
) -> FetchedAct | MissingAct:
    """Fetch one act as XHTML. A gap comes back as a `MissingAct`, never as an exception.

    Final acts answer 200. Proposals answer 300 with a list of streams: the act stream is
    fetched, then each annex stream. A lost annex is recorded in `annex_gaps` rather than
    failing the act. With annexes, `sha256` covers the act and annex bodies in stream order,
    so it still identifies exactly the bytes the text came from. `language` is the
    three-letter code CELLAR negotiates on.
    """
    url = celex_url(celex)
    headers = {"Accept": ACT_ACCEPT, "Accept-Language": language}
    annex_urls: tuple[str, ...] = ()
    try:
        response = fetcher.get(
            url, refresh=refresh, headers=headers, accept_status=(HTTP_MULTIPLE_CHOICES,)
        )
        if response.metadata.status == HTTP_MULTIPLE_CHOICES:
            stream = act_stream_url(response.body)
            if stream is None:
                reason = "CELLAR listed several streams and none is recognisable as the act"
                return MissingAct(celex, url, language, "failed", reason, HTTP_MULTIPLE_CHOICES)
            annex_urls = annex_stream_urls(response.body)
            url = stream
            response = fetcher.get(url, refresh=refresh, headers=headers)
    except FetchError as error:
        status = "missing" if error.status == HTTP_NOT_FOUND else "failed"
        return MissingAct(celex, url, language, status, error.reason, error.status)
    annexes: list[bytes] = []
    gaps: list[str] = []
    for annex_url in annex_urls:
        try:
            annexes.append(fetcher.get(annex_url, refresh=refresh, headers=headers).body)
        except FetchError as error:
            gaps.append(f"{annex_url}: {error.reason}")
    digest = hashlib.sha256(response.body)
    for annex in annexes:
        digest.update(annex)
    return FetchedAct(
        celex=celex,
        url=url,
        language=language,
        retrieved_at=response.metadata.fetched_at,
        sha256=digest.hexdigest(),
        media_type=response.metadata.content_type,
        body=response.body,
        annexes=tuple(annexes),
        annex_gaps=tuple(gaps),
    )


def cellar_document_id(celex: str) -> str:
    return document_id("cellar", celex)


def source_document(
    act: FetchedAct,
    *,
    procedure_id: str | None,
    extraction_status: ExtractionStatus,
    text_characters: int | None,
    title: str | None = None,
    published_at: datetime | None = None,
) -> SourceDocument:
    """The provenance record of a fetched act.

    `published_at` stays None unless the caller holds a date the document itself states
    (`SplitProvisions.published_on` for Official Journal acts): an undated document must
    not look dated.
    """
    return SourceDocument(
        document_id=cellar_document_id(act.celex),
        procedure_id=procedure_id,
        source_kind="cellar",
        url=act.url,
        title=title,
        published_at=published_at,
        retrieved_at=act.retrieved_at,
        sha256=act.sha256,
        media_type=act.media_type,
        language=act.language,
        extraction_status=extraction_status,
        extraction_method=EXTRACTION_METHOD,
        text_characters=text_characters,
        reuse_terms=REUSE_TERMS,
    )


# --- Text and provisions ----------------------------------------------------------------

_VOID_TAGS = frozenset({"img", "col", "hr", "meta", "link", "input", "area", "base", "wbr"})
_SKIPPED_TAGS = frozenset({"head", "script", "style"})
_BLOCK_TAGS = frozenset(
    {
        "body", "div", "p", "table", "tbody", "thead", "tr", "td", "th", "ul", "ol", "li",
        "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6", "section", "blockquote",
    }
)  # fmt: skip
# Word exports put a list number in its own span with no space before the text.
_NUMBER_CLASS = "num"
_ARTICLE_TITLE_CLASSES = frozenset({"oj-ti-art", "oj-sti-art"})
# Headings of a proposal: the title under "Article N" and the titles of its divisions.
_HEADING_CLASSES = frozenset({"SectionTitle", "ChapterTitle", "Titrearticle", "Articletitle"})
# A footnote call ("(5)" in the Official Journal, "62" in a proposal) interrupts the
# sentence it sits in; the footnotes themselves stay in the document text.
_NOTE_CALL_CLASS = "footnoteRef"
_NOTE_CALL_ID = "ntc"
# Private markers that cannot occur in parsed text: a <br/>, and "drop the space before".
_LINE_BREAK = "\x00"
_EAT_SPACE_BEFORE = "\x01"
_SPACE_BEFORE_NOTE = re.compile(r"\s*\x01")
_PUBLICATION_DATE_CLASS = "oj-hd-date"

_ELI_ID = re.compile(r"(rct|art|anx)_([0-9A-Za-z]+)")
_ELI_KINDS: dict[str, tuple[ProvisionKind, str]] = {
    "rct": ("recital", "Recital"),
    "art": ("article", "Article"),
    "anx": ("annex", "Annex"),
}
# A block that is only a list label ("(a)", "12.", a dash) belongs on the line it labels.
_MARKER = re.compile(r"\(\w{1,6}\)|\w{1,4}[.)]|[\u2014\u2013-]")
_ARTICLE_HEADING = re.compile(r"Article\s+(\d+[a-z]{0,2})")
_RECITAL_START = re.compile(r"\((\d+)\)\s*(?=\S)")
_PARAGRAPH_START = re.compile(r"(\d+)\.\s+(?=\S)")
_RECITALS_OPEN = re.compile(r"Whereas\b")
_RECITALS_CLOSE = re.compile(r"HA(VE|S) ADOPTED")
# Where the enacting terms stop in a proposal; the financial statement follows.
_ARTICLES_CLOSE = re.compile(r"Done at |This (Regulation|Decision) shall be binding")
_OJ_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")
# The heading line of one annex of a proposal: "ANNEX", "ANNEX I", "ANNEX 2". The cover page
# says "ANNEXES" and a cross-reference says "Annex III", so neither opens an annex.
_ANNEX_HEADING = re.compile(r"ANNEX(?:\s+([IVXLC]+|\d+[a-z]?))?")
NO_ANNEX_HEADING = "An annex stream with no 'ANNEX' heading line; its text is not split"

NO_STRUCTURE = (
    "No provision structure recognised: no ELI subdivision ids (rct_, art_, anx_) "
    "and no English 'Article N' headings"
)


@dataclass(frozen=True)
class _Block:
    """One paragraph-level run of text with the classes and ids of its ancestors."""

    text: str
    classes: frozenset[str]
    ids: tuple[str, ...]


class _Element(NamedTuple):
    tag: str
    identifier: str | None
    classes: frozenset[str]
    # Its text is left out: document head, scripts, and footnote calls inside sentences.
    skipped: bool


class _BlockParser(HTMLParser):
    """Turns markup into text blocks. Tolerates unclosed and stray tags: it never raises."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[_Block] = []
        self._open: list[_Element] = []
        self._parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self._parts.append(_LINE_BREAK)
        if tag == "br" or tag in _VOID_TAGS:
            return
        if tag in _BLOCK_TAGS:
            self._flush()
        attributes = dict(attrs)
        identifier = attributes.get("id")
        classes = frozenset((attributes.get("class") or "").split())
        note = tag == "a" and (
            _NOTE_CALL_CLASS in classes or (identifier or "").startswith(_NOTE_CALL_ID)
        )
        if note:
            self._parts.append(_EAT_SPACE_BEFORE)
        skipped = note or tag in _SKIPPED_TAGS
        self._skipping += skipped
        self._open.append(_Element(tag, identifier, classes, skipped))

    def handle_endtag(self, tag: str) -> None:
        if all(tag != element.tag for element in self._open):
            return
        if tag in _BLOCK_TAGS:
            self._flush()
        while True:
            element = self._open.pop()
            self._skipping -= element.skipped
            if element.tag == tag:
                break
        if _NUMBER_CLASS in element.classes:
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self._parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        raw = _SPACE_BEFORE_NOTE.sub("", "".join(self._parts))
        lines = (" ".join(line.split()) for line in raw.split(_LINE_BREAK))
        text = "\n".join(line for line in lines if line)
        self._parts.clear()
        if text:
            classes = frozenset[str]().union(*(element.classes for element in self._open))
            ids = tuple(element.identifier for element in self._open if element.identifier)
            self.blocks.append(_Block(text, classes, ids))


class SplitProvisions(NamedTuple):
    """The act's text, its provisions, and why there are none when there are none."""

    document_text: DocumentText
    provisions: tuple[ArticleVersion, ...]
    reason: str | None
    # The Official Journal date printed in the act's header; None for a proposal.
    published_on: date | None
    # Why an annex stream gave no provisions; empty when every annex stream was split.
    annex_reasons: tuple[str, ...] = ()


type _Section = tuple[ProvisionKind, str, list[_Block]]


def _join(blocks: Iterable[_Block]) -> str:
    """One block per line, with a bare list label kept on the line of the text it labels.

    The document text and every provision text are built by this one function from
    contiguous blocks, so a provision's text is a substring of the document text.
    """
    pieces: list[str] = []
    glue = ""
    for block in blocks:
        pieces.append(glue + block.text)
        glue = " " if _MARKER.fullmatch(block.text) else "\n"
    return "".join(pieces)


def _eli_section(block: _Block) -> tuple[ProvisionKind, str] | None:
    """The outermost ELI subdivision a block sits in, so a quoted article stays inside."""
    for identifier in block.ids:
        match = _ELI_ID.fullmatch(identifier)
        if match is not None:
            kind, word = _ELI_KINDS[match[1]]
            return kind, f"{word} {match[2]}"
    return None


def _eli_sections(blocks: Iterable[_Block]) -> list[_Section]:
    sections: dict[tuple[ProvisionKind, str], list[_Block]] = {}
    for block in blocks:
        key = _eli_section(block)
        if key is not None and not block.classes & _ARTICLE_TITLE_CLASSES:
            sections.setdefault(key, []).append(block)
    return [(kind, label, members) for (kind, label), members in sections.items()]


def _text_sections(blocks: Iterable[_Block]) -> list[_Section]:
    """Read recitals and articles from an English proposal with no structural ids.

    Recitals count only between "Whereas:" and the enacting formula, and articles end at
    "Done at", so the explanatory memorandum before and the financial statement after
    are never mistaken for the law. A heading whose number was already seen is a quoted
    article inside an amending provision and stays in the text of the article quoting it.
    """
    sections: list[_Section] = []
    seen: set[str] = set()
    zone: Literal["front", "recitals", "articles", "end"] = "front"
    for block in blocks:
        heading = _ARTICLE_HEADING.fullmatch(block.text.split("\n", 1)[0])
        if zone == "end":
            break
        if heading is not None and heading[1] not in seen:
            seen.add(heading[1])
            sections.append(("article", f"Article {heading[1]}", []))
            zone = "articles"
        elif zone == "articles":
            if _ARTICLES_CLOSE.match(block.text):
                zone = "end"
            elif not block.classes & _HEADING_CLASSES:
                sections[-1][2].append(block)
        elif _RECITALS_OPEN.match(block.text):
            zone = "recitals"
        elif zone == "recitals":
            recital = _RECITAL_START.match(block.text)
            if _RECITALS_CLOSE.search(block.text):
                zone = "front"
            elif recital is not None and f"({recital[1]})" not in seen:
                seen.add(f"({recital[1]})")
                sections.append(("recital", f"Recital {recital[1]}", [block]))
            elif sections:
                sections[-1][2].append(block)
    return sections


def _paragraphs(label: str, blocks: Iterable[_Block]) -> list[tuple[ProvisionKind, str, str]]:
    """Split an article at "1. ", "2. " ... taken in sequence.

    The sequence test keeps a numbered list inside a paragraph (or a quoted, renumbered
    paragraph in an amending article) from opening a paragraph of its own. Text before
    paragraph 1, or an article with no numbered paragraphs, is the article itself.
    """
    groups: list[tuple[int | None, list[_Block]]] = []
    expected = 1
    for block in blocks:
        start = _PARAGRAPH_START.match(block.text)
        if start is not None and int(start[1]) == expected:
            groups.append((expected, [block]))
            expected += 1
        elif groups:
            groups[-1][1].append(block)
        else:
            groups.append((None, [block]))
    provisions: list[tuple[ProvisionKind, str, str]] = []
    for number, members in groups:
        text = _join(members)
        if number is None:
            provisions.append(("article", label, text))
        else:
            provisions.append(
                ("paragraph", f"{label}({number})", _PARAGRAPH_START.sub("", text, 1))
            )
    return provisions


def _provisions(sections: Iterable[_Section]) -> list[tuple[ProvisionKind, str, str]]:
    provisions: list[tuple[ProvisionKind, str, str]] = []
    for kind, label, blocks in sections:
        if kind == "article":
            provisions.extend(_paragraphs(label, blocks))
        elif kind == "recital":
            provisions.append((kind, label, _RECITAL_START.sub("", _join(blocks), 1)))
        else:
            provisions.append((kind, label, _join(blocks)))
    return provisions


def _annex_sections(blocks: Iterable[_Block]) -> list[_Section]:
    """Split a proposal's annex stream at each "ANNEX I" heading; the cover page is dropped.

    The heading block opens the annex and stays in its text, as the Official Journal's
    annex container does, so the two stages' annexes compare like for like.
    """
    sections: list[_Section] = []
    for block in blocks:
        heading = _ANNEX_HEADING.fullmatch(block.text.split("\n", 1)[0])
        if heading is not None:
            label = f"Annex {heading[1]}" if heading[1] else "Annex"
            sections.append(("annex", label, [block]))
        elif sections:
            sections[-1][2].append(block)
    return sections


def _blocks_of(markup_bytes: bytes, what: str) -> list[_Block]:
    try:
        markup = markup_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CellarError(f"The text of {what} is not UTF-8") from error
    parser = _BlockParser()
    parser.feed(markup)
    parser.close()
    return parser.blocks


def _published_on(blocks: Iterable[_Block]) -> date | None:
    for block in blocks:
        match = _OJ_DATE.fullmatch(block.text)
        if match is not None and _PUBLICATION_DATE_CLASS in block.classes:
            try:
                return date(int(match[3]), int(match[2]), int(match[1]))
            except ValueError:
                # "31.2.2024" has the shape of a date and is not one: stay undated.
                return None
    return None


def split_provisions(
    xhtml_bytes: bytes,
    *,
    procedure_id: str,
    celex: str,
    stage: ArticleStage,
    document_id: str,
    version_date: date | None,
    annexes: Sequence[bytes] = (),
) -> SplitProvisions:
    """Extract the act's plain text and split it into recitals, articles and paragraphs.

    `annexes` are a proposal's annex streams: their text follows the act's in the document
    text and each "ANNEX I" heading opens one annex provision. Linear in the size of the
    document. `version_date` None takes the Official Journal date printed in the act, when
    there is one. Every `article_id` is unique within the act: a repeated label gets a
    numeric suffix rather than overwriting the first.
    """
    blocks = _blocks_of(xhtml_bytes, celex)
    published_on = _published_on(blocks)
    structured = any(_eli_section(block) is not None for block in blocks)
    sections = _eli_sections(blocks) if structured else _text_sections(blocks)
    annex_reasons: list[str] = []
    for number, annex in enumerate(annexes, start=1):
        annex_blocks = _blocks_of(annex, f"{celex} annex stream {number}")
        found = _annex_sections(annex_blocks)
        if annex_blocks and not found:
            annex_reasons.append(f"{celex} annex stream {number}: {NO_ANNEX_HEADING}")
        sections.extend(found)
        blocks.extend(annex_blocks)
    document_text = DocumentText(document_id=document_id, text=_join(blocks))
    used: dict[str, int] = {}
    records: list[ArticleVersion] = []
    for kind, provision, text in _provisions(sections):
        slug = id_part(provision).lower()
        used[slug] = used.get(slug, 0) + 1
        suffix = "" if used[slug] == 1 else f"-{used[slug]}"
        records.append(
            ArticleVersion(
                article_id=f"art:{id_part(celex)}:{slug}{suffix}",
                procedure_id=procedure_id,
                document_id=document_id,
                stage=stage,
                provision=provision,
                kind=kind,
                text=text,
                version_date=version_date or published_on,
            )
        )
    reason = None if records else NO_STRUCTURE
    return SplitProvisions(
        document_text, tuple(records), reason, published_on, tuple(annex_reasons)
    )
