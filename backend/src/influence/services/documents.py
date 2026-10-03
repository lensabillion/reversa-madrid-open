"""Bounded local extraction, without OCR, network access, or document action execution."""

import re
from io import BytesIO
from itertools import product
from typing import NamedTuple

from pypdf import PdfReader, apply_configuration
from pypdf.errors import LimitReachedError, PyPdfError

from influence.schemas.documents import DocumentFormat, ExtractedDocument, ExtractedPage

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PAGES = 100
MAX_TEXT_CHARACTERS = 500_000
MAX_PAGE_STREAM_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_STREAM_BYTES = 16 * 1024 * 1024


# Presentation forms of Latin ligatures expand to their letters with no ambiguity.
_LIGATURES = str.maketrans(
    {
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\ufb05": "st",
        "\ufb06": "st",
    }
)
# A ligature glyph with no Unicode mapping in its font comes out of pypdf as U+0000
# ("signi\x00cant"). Candidates in order of frequency in English: ties go to the first.
_GLYPH_GUESSES = ("fi", "fl", "ff", "ffi", "ffl")
# Words with more lost glyphs than this are not guessed: 5**3 candidates is the most tried.
_MAX_LOST_GLYPHS_PER_WORD = 3
_BROKEN_WORD = re.compile(r"[^\W\d_]*(?:\x00[^\W\d_]*)+")
_WORD = re.compile(r"[^\W\d_]+")
# Lowercase word parts that hold a ligature, from English, French and German policy text.
# A guess is accepted only when a part covers the whole guessed ligature, so a short part
# never supports a longer ligature next to it ("offic" beats "fic" for "o\x00cial").
_LIGATURE_WORD_PARTS: frozenset[str] = frozenset(
    {
        # fi
        "fiel", "fil", "final", "financ", "find", "fine", "firm", "first", "fisc", "fit",
        "fix", "fic", "figur", "defin", "benefi", "profit", "profil", "confid", "artific",
        "scientif", "signific", "magnific", "specific", "specifi", "modific", "modifi",
        "notific", "notifi", "certific", "certifi", "classific", "classifi", "identif",
        "verific", "verifi", "justif", "qualif", "clarif", "simplif", "quantif", "ratif",
        "rectif", "amplif", "diversif", "intensif", "unifi", "satisf", "spezifi", "afin",
        "häufig",
        # fl
        "flow", "flex", "influen", "einfluss", "conflict", "konflikt", "reflect", "inflat",
        "deflat", "flag", "fleet", "float", "flight", "flood", "flaw", "fluctu", "fluid",
        "flat", "superflu", "pflicht",
        # ff
        "off", "effect", "effort", "offer", "differ", "affect", "staff", "tariff", "suffer",
        "afford", "buffer", "diffus", "stuff", "öffentl", "griff", "betriff", "schaff",
        "hoff", "treff",
        # ffi
        "offic", "suffici", "suffis", "traffic", "diffic", "effici", "effica", "affili",
        "affirm",
        # ffl
        "afflict", "affluen", "shuffl", "baffl",
    }
)  # fmt: skip


class GlyphRepair(NamedTuple):
    """Text with ligature glyphs restored, and how many lost glyphs were guessed or not."""

    text: str
    guessed: int
    unresolved: int


def _part_support(word: str, start: int, end: int) -> int:
    """Length of the longest known word part covering `word[start:end]`; 0 when none."""
    best = 0
    for part in _LIGATURE_WORD_PARTS:
        index = word.find(part)
        while index != -1:
            if index <= start and index + len(part) >= end:
                best = max(best, len(part))
            index = word.find(part, index + 1)
    return best


def _guess_word(pieces: list[str], vocabulary: frozenset[str]) -> str | None:
    """The likeliest spelling of a word whose ligatures were lost between `pieces`.

    A spelling found elsewhere in the same document wins; otherwise each guessed ligature
    must be covered by a known word part, and the longest total support wins. None when
    no spelling qualifies. Cost: 5**k candidates for k lost glyphs, k <= 3.
    """
    best: tuple[int, str] | None = None
    for ligatures in product(_GLYPH_GUESSES, repeat=len(pieces) - 1):
        word = pieces[0]
        spans: list[tuple[int, int]] = []
        for ligature, piece in zip(ligatures, pieces[1:], strict=True):
            spans.append((len(word), len(word) + len(ligature)))
            word += ligature + piece
        lowered = word.lower()
        if lowered in vocabulary:
            return word
        supports = [_part_support(lowered, start, end) for start, end in spans]
        score = sum(supports) if all(supports) else 0
        if score and (best is None or score > best[0]):
            best = (score, word)
    return None if best is None else best[1]


def repair_ligatures(text: str, vocabulary: frozenset[str]) -> GlyphRepair:
    """Expand ligature code points; restore ligature glyphs pypdf extracted as U+0000.

    Some PDF fonts map the fi, fl, ff, ffi and ffl glyphs to no character, so pypdf
    returns U+0000 inside the word and every word match misses it. A lost glyph is
    restored by `_guess_word` and counted as guessed; one it cannot place becomes a space
    and is counted as unresolved, never dropped silently. `vocabulary` holds the
    lowercase words of the whole document, read before repair.
    """
    text = text.translate(_LIGATURES)
    guessed = 0
    unresolved = 0

    def restore(match: re.Match[str]) -> str:
        nonlocal guessed, unresolved
        pieces = match.group().split("\x00")
        lost = len(pieces) - 1
        word = None
        if lost <= _MAX_LOST_GLYPHS_PER_WORD and any(pieces):
            word = _guess_word(pieces, vocabulary)
        if word is None:
            unresolved += lost
            return " ".join(pieces)
        guessed += lost
        return word

    return GlyphRepair(_BROKEN_WORD.sub(restore, text), guessed, unresolved)


def document_vocabulary(texts: tuple[str, ...]) -> frozenset[str]:
    """The lowercase words of a document, the first evidence for a lost ligature."""
    return frozenset(
        word.lower() for text in texts for word in _WORD.findall(text.translate(_LIGATURES))
    )


class DocumentExtractionError(ValueError):
    """A document failed validation; callers can expose the code and safe message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _pdf_pages(content: bytes) -> tuple[ExtractedPage, ...]:
    # Context-local limits avoid races between requests. Disable external JBIG2 tools;
    # text extraction never needs image conversion, JavaScript, attachments, or URLs.
    with apply_configuration(
        maximum_declared_stream_length=MAX_PAGE_STREAM_BYTES,
        array_based_stream_maximum_output_length=MAX_PAGE_STREAM_BYTES,
        zlib_maximum_output_length=MAX_PAGE_STREAM_BYTES,
        lzw_maximum_output_length=MAX_PAGE_STREAM_BYTES,
        run_length_maximum_output_length=MAX_PAGE_STREAM_BYTES,
        image_maximum_buffer_size=MAX_PAGE_STREAM_BYTES,
        page_tree_maximum_entries=MAX_PAGES * 4,
        xform_maximum_invocations_per_extraction=100,
        jbig2dec_binary=None,
    ):
        # Not strict: real submissions are often saved incrementally or edited, leaving an
        # xref offset a few bytes off that pypdf repairs. Strict parsing rejected them
        # though their text reads intact; the limits above still bound the work.
        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise DocumentExtractionError("encrypted_pdf", "Encrypted PDFs are not supported.")
        if len(reader.pages) > MAX_PAGES:
            raise DocumentExtractionError(
                "too_many_pages", f"PDFs must have at most {MAX_PAGES} pages."
            )
        pages: list[ExtractedPage] = []
        stream_bytes = 0
        characters = 0
        for number, page in enumerate(reader.pages, start=1):
            contents = page.get_contents()
            if contents is not None:
                size = len(contents.get_data())
                stream_bytes += size
                if size > MAX_PAGE_STREAM_BYTES or stream_bytes > MAX_DOCUMENT_STREAM_BYTES:
                    raise DocumentExtractionError(
                        "pdf_stream_too_large", "PDF content streams exceed extraction limits."
                    )
            text = page.extract_text()
            characters += len(text)
            if characters > MAX_TEXT_CHARACTERS:
                raise DocumentExtractionError(
                    "text_too_large", "Extracted text exceeds 500,000 characters."
                )
            pages.append(ExtractedPage(page=number, text=text))
        return tuple(pages)


def extract_document(content: bytes, format: DocumentFormat) -> ExtractedDocument:
    """Retain source text and page boundaries; never replace missing text with a guess.

    PDF parsing has input-dependent cost. Limits bound uploads, pages, expanded content
    streams and returned text, but are not a hard memory/CPU sandbox for hostile PDFs.
    """
    if len(content) > MAX_UPLOAD_BYTES:
        raise DocumentExtractionError("document_too_large", "Documents must be at most 8 MiB.")
    if not content:
        raise DocumentExtractionError("empty_document", "The document is empty.")
    warnings: list[str] = []
    guessed = 0
    unresolved = 0
    if format == "text":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise DocumentExtractionError(
                "invalid_utf8", "Text documents must use UTF-8 encoding."
            ) from error
        if len(text) > MAX_TEXT_CHARACTERS:
            raise DocumentExtractionError("text_too_large", "Text exceeds 500,000 characters.")
        if not text.strip():
            raise DocumentExtractionError("empty_document", "The document contains no text.")
        pages = (ExtractedPage(page=1, text=text),)
    else:
        try:
            pages = _pdf_pages(content)
        except DocumentExtractionError:
            raise
        except LimitReachedError as error:
            raise DocumentExtractionError(
                "pdf_stream_too_large", "PDF structure or content exceeds extraction limits."
            ) from error
        except (
            PyPdfError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            AttributeError,
            RecursionError,
            NotImplementedError,
        ) as error:
            raise DocumentExtractionError(
                "invalid_pdf", "The PDF is malformed or cannot be read."
            ) from error
        if not pages:
            raise DocumentExtractionError("empty_document", "The PDF contains no pages.")
        # Repaired before anything cuts passages or spans: the stored text is this one.
        vocabulary = document_vocabulary(tuple(page.text for page in pages))
        repaired: list[ExtractedPage] = []
        for page in pages:
            repair = repair_ligatures(page.text, vocabulary)
            guessed += repair.guessed
            unresolved += repair.unresolved
            repaired.append(ExtractedPage(page=page.page, text=repair.text))
        pages = tuple(repaired)
        if not any(page.text.strip() for page in pages):
            raise DocumentExtractionError(
                "ocr_required", "The PDF has no extractable text; it may be blank or require OCR."
            )
        warnings.append(
            "PDF text order may differ from visual layout; "
            "columns and tables require verification. OCR is not performed."
        )
        warnings.extend(
            f"Page {page.page} has no extractable text; it may be blank or require OCR."
            for page in pages
            if not page.text.strip()
        )
        if guessed:
            warnings.append(
                f"{guessed} ligature glyph(s) (fi, fl, ff, ffi, ffl) had no character in "
                "the PDF font and were restored by a word guess."
            )
        if unresolved:
            warnings.append(
                f"{unresolved} glyph(s) had no character in the PDF font and no word guess "
                "fit; each was replaced by a space."
            )
    return ExtractedDocument(
        format=format,
        pages=pages,
        warnings=tuple(warnings),
        character_count=sum(len(page.text) for page in pages),
        glyphs_guessed=guessed,
        glyphs_unresolved=unresolved,
    )
