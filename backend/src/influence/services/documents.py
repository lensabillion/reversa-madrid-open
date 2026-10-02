"""Bounded local extraction, without OCR, network access, or document action execution."""

from io import BytesIO

from pypdf import PdfReader, apply_configuration
from pypdf.errors import LimitReachedError, PyPdfError

from influence.schemas.documents import DocumentFormat, ExtractedDocument, ExtractedPage

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PAGES = 100
MAX_TEXT_CHARACTERS = 500_000
MAX_PAGE_STREAM_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_STREAM_BYTES = 16 * 1024 * 1024


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
        reader = PdfReader(BytesIO(content), strict=True)
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
    return ExtractedDocument(
        format=format,
        pages=pages,
        warnings=tuple(warnings),
        character_count=sum(len(page.text) for page in pages),
    )
