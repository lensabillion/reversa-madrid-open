"""Document extraction checks actual PDF bytes and explicit upload failures."""

import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfWriter, get_configuration
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)
from starlette.types import Message

from influence.api import create_app
from influence.routers import documents as router
from influence.schemas.documents import DocumentFormat, ExtractedDocument
from influence.services import documents
from influence.services.documents import (
    DocumentExtractionError,
    GlyphRepair,
    document_vocabulary,
    extract_document,
    repair_ligatures,
)


def make_pdf(
    texts: tuple[str, ...],
    *,
    encrypted: bool = False,
    compressed: bool = False,
    fi_glyph_code: int | None = None,
) -> bytes:
    """`fi_glyph_code` maps that byte to the font's /fi ligature glyph by /Differences."""
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        if fi_glyph_code is not None:
            font[NameObject("/Encoding")] = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Encoding"),
                    NameObject("/Differences"): ArrayObject(
                        [NumberObject(fi_glyph_code), NameObject("/fi")]
                    ),
                }
            )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
            }
        )
        if text:
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
            page.replace_contents(ContentStream(stream, writer))
            if compressed:
                page.compress_content_streams()
    if encrypted:
        writer.encrypt("password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_preserves_page_numbers_text_and_blank_page_warning() -> None:
    result = extract_document(make_pdf(("Article 1: retain 2.5%", "", "shall not disclose")), "pdf")
    assert [(page.page, page.text) for page in result.pages] == [
        (1, "Article 1: retain 2.5%"),
        (2, ""),
        (3, "shall not disclose"),
    ]
    assert result.character_count == len("Article 1: retain 2.5%shall not disclose")
    assert any("Page 2" in warning for warning in result.warnings)


def test_text_preserves_unicode_and_whitespace() -> None:
    text = "\nCafé 😀 shall not disclose.\n"
    result = extract_document(text.encode(), "text")
    assert result.model_dump() == {
        "format": "text",
        "pages": ({"page": 1, "text": text},),
        "warnings": (),
        "character_count": len(text),
        "glyphs_guessed": 0,
        "glyphs_unresolved": 0,
    }


@pytest.mark.parametrize(
    ("body", "format", "code"),
    [
        (b"", "text", "empty_document"),
        (b" \n", "text", "empty_document"),
        (b"\xff", "text", "invalid_utf8"),
        (b"not a pdf", "pdf", "invalid_pdf"),
        (make_pdf(("secret",), encrypted=True), "pdf", "encrypted_pdf"),
        (make_pdf(("",)), "pdf", "ocr_required"),
        (make_pdf(()), "pdf", "empty_document"),
    ],
)
def test_failed_documents_do_not_fabricate_text(
    body: bytes, format: DocumentFormat, code: str
) -> None:
    with pytest.raises(DocumentExtractionError) as error:
        extract_document(body, format)
    assert error.value.code == code


def test_http_raw_text_and_pdf_contract() -> None:
    client = TestClient(create_app())
    for media in ("text/plain; charset=utf-8", "text/markdown"):
        response = client.post(
            "/api/v1/documents/extract", content=b"# Legal text", headers={"Content-Type": media}
        )
        assert response.status_code == 200
        assert response.json()["pages"] == [{"page": 1, "text": "# Legal text"}]
    response = client.post(
        "/api/v1/documents/extract",
        content=make_pdf(("Proposed clause",)),
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 200
    assert response.json()["format"] == "pdf"
    assert response.json()["pages"] == [{"page": 1, "text": "Proposed clause"}]


def test_http_rejects_unsupported_types_and_malformed_uploads() -> None:
    client = TestClient(create_app())
    unsupported = client.post("/api/v1/documents/extract", content=b"text")
    assert unsupported.status_code == 415
    assert unsupported.json()["detail"]["code"] == "unsupported_media_type"
    invalid = client.post(
        "/api/v1/documents/extract", content=b"bad PDF", headers={"Content-Type": "application/pdf"}
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_pdf"


def test_upload_and_text_size_limits() -> None:
    with pytest.raises(DocumentExtractionError, match="8 MiB") as error:
        extract_document(b"x" * (documents.MAX_UPLOAD_BYTES + 1), "text")
    assert error.value.code == "document_too_large"
    assert (
        extract_document(b"x" * documents.MAX_TEXT_CHARACTERS, "text").character_count
        == documents.MAX_TEXT_CHARACTERS
    )
    with pytest.raises(DocumentExtractionError) as error:
        extract_document(b"x" * (documents.MAX_TEXT_CHARACTERS + 1), "text")
    assert error.value.code == "text_too_large"


def test_pdf_page_and_extracted_text_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    body = make_pdf(("one", "two"))
    monkeypatch.setattr(documents, "MAX_PAGES", 1)
    with pytest.raises(DocumentExtractionError) as error:
        extract_document(body, "pdf")
    assert error.value.code == "too_many_pages"
    monkeypatch.setattr(documents, "MAX_PAGES", 2)
    monkeypatch.setattr(documents, "MAX_TEXT_CHARACTERS", 5)
    with pytest.raises(DocumentExtractionError) as error:
        extract_document(body, "pdf")
    assert error.value.code == "text_too_large"


def test_pdf_stream_limits_before_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    configuration = get_configuration()
    compressed = make_pdf(("x" * 1000,), compressed=True)
    monkeypatch.setattr(documents, "MAX_PAGE_STREAM_BYTES", 100)
    with pytest.raises(DocumentExtractionError) as error:
        extract_document(compressed, "pdf")
    assert error.value.code == "pdf_stream_too_large"
    assert get_configuration() == configuration
    monkeypatch.setattr(documents, "MAX_PAGE_STREAM_BYTES", 2000)
    monkeypatch.setattr(documents, "MAX_DOCUMENT_STREAM_BYTES", 50)
    with pytest.raises(DocumentExtractionError) as error:
        extract_document(make_pdf(("one", "two")), "pdf")
    assert error.value.code == "pdf_stream_too_large"


def test_http_stream_cap_and_service_limit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(router, "MAX_UPLOAD_BYTES", 8)
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/documents/extract",
        content=iter((b"abcde", b"fghi")),
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "document_too_large"
    monkeypatch.setattr(documents, "MAX_TEXT_CHARACTERS", 2)
    response = client.post(
        "/api/v1/documents/extract", content=b"abc", headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "text_too_large"


def test_stream_stops_before_reading_remainder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(router, "MAX_UPLOAD_BYTES", 8)
    events: list[Message] = [
        {"type": "http.request", "body": b"12345", "more_body": True},
        {"type": "http.request", "body": b"6789", "more_body": True},
        {"type": "http.request", "body": b"do not read", "more_body": False},
    ]

    async def receive() -> Message:
        return events.pop(0)

    request = Request({"type": "http", "headers": [(b"content-type", b"text/plain")]}, receive)
    with pytest.raises(HTTPException) as error:
        asyncio.run(router.extract(request))
    assert error.value.status_code == 413
    assert len(events) == 1


def test_extraction_runs_off_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    def check_thread(content: bytes, format: DocumentFormat) -> ExtractedDocument:
        with pytest.raises(RuntimeError, match="no running event loop"):
            asyncio.get_running_loop()
        return extract_document(content, format)

    monkeypatch.setattr(router, "extract_document", check_thread)
    response = TestClient(create_app()).post(
        "/api/v1/documents/extract", content=b"actual text", headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 200
    assert response.json()["pages"] == [{"page": 1, "text": "actual text"}]


def test_unsupported_pdf_filter_is_an_explicit_error() -> None:
    body = make_pdf(("clause",), compressed=True).replace(b"/FlateDecode", b"/BogusFilerX")
    with pytest.raises(DocumentExtractionError) as error:
        extract_document(body, "pdf")
    assert error.value.code == "invalid_pdf"


def test_document_contract_is_frozen_and_openapi_describes_raw_media() -> None:
    result = extract_document(b"clause", "text")
    with pytest.raises(ValidationError, match="frozen"):
        result.pages[0].text = "other"
    with pytest.raises(ValidationError, match="Extra inputs"):
        ExtractedDocument.model_validate({**result.model_dump(), "guessed_original": ""})
    schema = TestClient(create_app()).get("/openapi.json").json()
    upload = schema["paths"]["/api/v1/documents/extract"]["post"]
    assert set(upload["requestBody"]["content"]) == {
        "application/pdf",
        "text/plain",
        "text/markdown",
    }
    assert upload["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ExtractedDocument"
    }


def test_committed_organizers_brief_preserves_challenge_pages() -> None:
    brief = Path(__file__).resolve().parents[2] / "docs/brief/madrid-open-reversa-challenges.pdf"
    result = extract_document(brief.read_bytes(), "pdf")
    assert len(result.pages) == 16
    assert result.pages[11].page == 12
    assert "CHALLENGE 03" in result.pages[11].text
    assert "influence_score" in result.pages[12].text
    assert "p_adopted" in result.pages[12].text
    assert "60 amendment" in result.pages[13].text
    assert "20:00" in result.pages[14].text


NO_WORDS: frozenset[str] = frozenset()


def test_pdf_ligature_glyph_without_a_character_is_restored_and_warned() -> None:
    # The real failure (rev-obw8): the font gives the fi glyph no character, so pypdf
    # returns U+0000 and every word match misses "significant".
    result = extract_document(
        make_pdf(("Substantial modi\x00cations and signi\x00cant changes",)), "pdf"
    )
    assert result.pages[0].text == "Substantial modifications and significant changes"
    assert (result.glyphs_guessed, result.glyphs_unresolved) == (2, 0)
    assert result.character_count == len(result.pages[0].text)
    assert any("2 ligature glyph(s)" in warning for warning in result.warnings)
    assert not any("replaced by a space" in warning for warning in result.warnings)


def test_pdf_mapped_ligature_glyph_expands_to_letters_without_a_warning() -> None:
    result = extract_document(make_pdf(("signi\\001cant",), fi_glyph_code=1), "pdf")
    assert result.pages[0].text == "significant"
    assert (result.glyphs_guessed, result.glyphs_unresolved) == (0, 0)
    assert len(result.warnings) == 1


def test_pdf_glyph_that_fits_no_word_becomes_a_counted_space() -> None:
    result = extract_document(make_pdf(("Article 5 \x00 qx\x00zz applies",)), "pdf")
    assert result.pages[0].text == "Article 5   qx zz applies"
    assert (result.glyphs_guessed, result.glyphs_unresolved) == (0, 2)
    assert any("2 glyph(s)" in w and "replaced by a space" in w for w in result.warnings)


def test_the_document_vocabulary_spans_pages_and_wins_over_word_parts() -> None:
    # "fluff" holds no known word part, but page 2 spells it, so page 1 can be restored.
    result = extract_document(make_pdf(("Remove the \x00u\x00.", "Fluff stays.")), "pdf")
    assert result.pages[0].text == "Remove the fluff."
    assert result.glyphs_guessed == 2


@pytest.mark.parametrize(
    ("text", "repaired"),
    [
        ("\ufb00\ufb01\ufb02\ufb03\ufb04\ufb05\ufb06", GlyphRepair("fffiflffifflstst", 0, 0)),
        ("no glyph was lost", GlyphRepair("no glyph was lost", 0, 0)),
        ("signi\x00cant", GlyphRepair("significant", 1, 0)),
        ("Signi\x00cant", GlyphRepair("Significant", 1, 0)),
        ("\x00rst \x00nancial", GlyphRepair("first financial", 2, 0)),
        ("in\x00uence con\x00ict \x00exible", GlyphRepair("influence conflict flexible", 3, 0)),
        ("e\x00ective di\x00erent sta\x00", GlyphRepair("effective different staff", 3, 0)),
        ("o\x00cial su\x00cient e\x00cient", GlyphRepair("official sufficient efficient", 3, 0)),
        ("a\x00uent a\x00ict", GlyphRepair("affluent afflict", 2, 0)),
        ("Verp\x00ichtung", GlyphRepair("Verpflichtung", 1, 0)),
        ("speci\x00cally modi\x00ed", GlyphRepair("specifically modified", 2, 0)),
        ("a\x00b", GlyphRepair("a b", 0, 1)),
        ("1\x002", GlyphRepair("1 2", 0, 1)),
        ("\x00\x00", GlyphRepair("  ", 0, 2)),
        ("a\x00b\x00c\x00d\x00e", GlyphRepair("a b c d e", 0, 4)),
    ],
)
def test_repair_ligatures(text: str, repaired: GlyphRepair) -> None:
    assert repair_ligatures(text, NO_WORDS) == repaired


def test_two_lost_glyphs_in_one_word_need_support_for_both() -> None:
    # A made-up compound: each guessed ligature must sit inside a known word part.
    assert repair_ligatures("\x00rst\x00ow", NO_WORDS) == GlyphRepair("firstflow", 2, 0)
    assert repair_ligatures("signi\x00cant\x00qx", NO_WORDS) == GlyphRepair("signi cant qx", 0, 2)


def test_vocabulary_is_lowercase_words_with_ligatures_expanded() -> None:
    assert document_vocabulary(("Signi\x00cant ﬁeld, 2024", "Fluff")) == {
        "signi",
        "cant",
        "field",
        "fluff",
    }
    assert repair_ligatures("\x00u\x00", frozenset({"fluff"})) == GlyphRepair("fluff", 2, 0)
