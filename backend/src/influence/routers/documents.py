"""Stream bounded raw uploads, leaving extraction and validation to the service."""

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from influence.schemas.documents import DocumentFormat, ExtractedDocument
from influence.services.documents import MAX_UPLOAD_BYTES, DocumentExtractionError, extract_document

router = APIRouter(prefix="/api/v1")
_FORMATS: dict[str, DocumentFormat] = {
    "application/pdf": "pdf",
    "text/plain": "text",
    "text/markdown": "text",
}
_LIMIT_CODES = {"document_too_large", "too_many_pages", "text_too_large", "pdf_stream_too_large"}


@router.post(
    "/documents/extract",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media: {"schema": {"type": "string", "format": "binary"}} for media in _FORMATS
            },
        }
    },
)
async def extract(request: Request) -> ExtractedDocument:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    format = _FORMATS.get(media_type)
    if format is None:
        raise HTTPException(
            415,
            detail={
                "code": "unsupported_media_type",
                "message": "Use application/pdf, text/plain, or text/markdown.",
            },
        )
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                413,
                detail={
                    "code": "document_too_large",
                    "message": "Documents must be at most 8 MiB.",
                },
            )
        content.extend(chunk)
    try:
        return await run_in_threadpool(extract_document, bytes(content), format)
    except DocumentExtractionError as error:
        raise HTTPException(
            413 if error.code in _LIMIT_CODES else 422,
            detail={"code": error.code, "message": str(error)},
        ) from error
