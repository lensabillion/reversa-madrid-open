"""Have Your Say: the Commission's consultation feedback, joined to a law by COM reference.

The portal cannot be searched by COM number (`text=COM(2021)206` answers `general_error`),
and the initiative list carries only the initiative's own reference, not the references
of its publications. So the join key is built once: every initiative is fetched and its
publication references are indexed. Every response goes through the cache, which makes
the crawl resumable for free.

Private individuals are counted, never named: `firstName` and `surname` are never read,
and a citizen's `organization` is dropped.
"""

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import cast
from urllib.parse import quote
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, ValidationError

from influence.extraction.fetching import CachedFetcher, FetchError
from influence.extraction.files import write_bytes_atomic
from influence.schemas.atlas import (
    DocumentText,
    SourceDocument,
    document_id,
)
from influence.schemas.scoring import FrozenModel
from influence.services.documents import DocumentExtractionError, extract_document

BASE_URL = "https://ec.europa.eu/info/law/better-regulation"
# The list endpoint silently caps `size` at 100 (observed: size=500 returned 100 rows).
PAGE_SIZE = 100
TITLE_SEARCH_SIZE = 20
REUSE_TERMS = "Commission reuse policy, CC BY 4.0 (Decision 2011/833/EU)"
CITIZEN_USER_TYPES: frozenset[str] = frozenset({"EU_CITIZEN", "NON_EU_CITIZEN"})
FEEDBACK_METHOD = "hys_api:feedback_field"
ATTACHMENT_METHOD = "pypdf"
PAGE_SEPARATOR = "\n\n"

# The API writes naive local timestamps ("2021/08/06 23:57:37"). They are Brussels time:
# the AI Act feedback window closed at endDate "2021/08/06 23:59:59" and the last feedback
# is stamped 23:57:37 on that day, which read as UTC would fall after the deadline.
HYS_TIMEZONE = ZoneInfo("Europe/Brussels")
_DATE_FORMAT = "%Y/%m/%d %H:%M:%S"

_COM_REFERENCE = re.compile(r"(?<![A-Za-z])COM\s*[(/]\s*(\d{4})\s*[)/]\s*0*(\d+)", re.IGNORECASE)
# `trNumber` is typed by the respondent ("TR 435520331024-09", "ID#43763731235-75"). A
# well-formed identifier inside the field is read; anything else is not repaired.
_REGISTER_ID = re.compile(r"(?<!\d)\d{6,}-\d{2}(?!\d)")
# JSON escapes and PDF fonts can yield lone surrogates, which UTF-8 cannot encode.
_SURROGATES = re.compile("[\ud800-\udfff]")

type Progress = Callable[[int, int | None], None]
type ErrorSink = Callable[[int, HysError], None]


class HysError(RuntimeError):
    """Have Your Say did not give a usable answer; the caller records a coverage gap."""


class HysUnavailable(HysError):  # noqa: N818 - the name is the contract the pipeline uses.
    """The publication exists but its responses are not served by this API.

    Questionnaire consultations hosted elsewhere (the AI White Paper, publication 25429)
    answer `bad_request`. That is a property of the source, not a transient failure.
    """


class Publication(FrozenModel):
    """One stage of an initiative: a roadmap, a public consultation or the proposal."""

    publication_id: int
    type: str | None
    reference: str | None
    com_reference: str | None
    # None means the source did not say, which is different from a counted zero.
    total_feedback: int | None
    published_at: AwareDatetime | None
    adopted_at: AwareDatetime | None
    feedback_end_at: AwareDatetime | None


class IndexEntry(FrozenModel):
    initiative_id: int
    short_title: str | None
    reference: str | None
    com_references: tuple[str, ...]
    publications: tuple[Publication, ...]


class Attachment(FrozenModel):
    """A file attached to a feedback. The API serves it as a PDF whatever was uploaded."""

    attachment_id: int | None
    document_id: str
    file_name: str | None
    # The feed leaves `pages` null; it is known only after the file is read.
    pages: int | None = None


class FeedbackItem(FrozenModel):
    """One submission, with what the actor resolver needs and no personal names."""

    feedback_id: int
    publication_id: int
    reference: str | None
    com_reference: str | None
    submitted_at: AwareDatetime | None
    text: str
    language: str | None
    user_type: str | None
    country: str | None
    company_size: str | None
    organization: str | None
    register_id: str | None
    # What the respondent typed, kept for the actor resolver; None for citizens.
    register_id_raw: str | None
    # The Commission's machine translation into English, when it differs from `text`.
    english_translation: str | None
    attachments: tuple[Attachment, ...]

    @property
    def is_citizen(self) -> bool:
        return self.user_type in CITIZEN_USER_TYPES


# --- URLs -------------------------------------------------------------------------------


def search_url(*, page: int, size: int = PAGE_SIZE, text: str | None = None) -> str:
    query = f"page={page}&size={size}&language=EN"
    if text is not None:
        query = f"text={quote(text, safe='')}&{query}"
    return f"{BASE_URL}/brpapi/searchInitiatives?{query}"


def initiative_url(initiative_id: int) -> str:
    return f"{BASE_URL}/brpapi/groupInitiatives/{initiative_id}?language=EN"


def feedback_url(publication_id: int, page: int) -> str:
    return f"{BASE_URL}/api/allFeedback?publicationId={publication_id}&page={page}&size={PAGE_SIZE}"


def download_url(hys_document_id: str) -> str:
    return f"{BASE_URL}/api/download/{quote(hys_document_id, safe='')}"


# --- Small typed readers over untyped JSON ----------------------------------------------


def _object(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise HysError(f"Expected a JSON object for {what}")
    return cast("dict[str, object]", value)


def _objects(value: object, what: str) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HysError(f"Expected a JSON array for {what}")
    return [_object(item, what) for item in cast("list[object]", value)]


def _text(value: object) -> str | None:
    """A non-blank string, stripped; anything else is unknown."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _integer(value: object) -> int | None:
    """The list endpoint writes identifiers as floats (19418.0); accept whole numbers only."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _required_integer(value: object, what: str) -> int:
    number = _integer(value)
    if number is None:
        raise HysError(f"Missing integer {what}")
    return number


def _clean(text: str) -> str:
    return _SURROGATES.sub("\ufffd", text)


def parse_hys_datetime(value: object) -> datetime | None:
    """Unparseable stays None: an undated submission is never eligible as an origin."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), _DATE_FORMAT).replace(tzinfo=HYS_TIMEZONE)
    except ValueError:
        return None


def normalise_com_reference(value: str | None) -> str | None:
    """`COM(YYYY)N` without zero padding or suffixes; None when no COM number is present."""
    if value is None:
        return None
    match = _COM_REFERENCE.search(value)
    if match is None:
        return None
    return f"COM({match.group(1)}){int(match.group(2))}"


def _get_json(fetcher: CachedFetcher, url: str, *, refresh: bool = False) -> dict[str, object]:
    try:
        response = fetcher.get(url, refresh=refresh)
    except FetchError as error:
        raise HysError(f"Have Your Say request failed: {error}") from error
    return _decode(response.body, url)


def _decode(body: bytes, url: str) -> dict[str, object]:
    try:
        value: object = json.loads(body)
    except ValueError as error:
        raise HysError(f"{url}: response is not JSON ({body[:40]!r})") from error
    return _object(value, url)


# --- Index ------------------------------------------------------------------------------


def _publication(raw: dict[str, object]) -> Publication:
    reference = _text(raw.get("reference"))
    return Publication(
        publication_id=_required_integer(raw.get("id"), "publication id"),
        type=_text(raw.get("type")),
        reference=reference,
        com_reference=normalise_com_reference(reference),
        total_feedback=_integer(raw.get("totalFeedback")),
        published_at=parse_hys_datetime(raw.get("publishedDate")),
        adopted_at=parse_hys_datetime(raw.get("adoptionDate")),
        feedback_end_at=parse_hys_datetime(raw.get("endDate")),
    )


def fetch_initiative(
    fetcher: CachedFetcher, initiative_id: int, *, refresh: bool = False
) -> IndexEntry:
    """One initiative with its publications, reduced to what the join needs."""
    data = _get_json(fetcher, initiative_url(initiative_id), refresh=refresh)
    publications = tuple(
        _publication(raw) for raw in _objects(data.get("publications"), "publications")
    )
    references = dict.fromkeys(
        item.com_reference for item in publications if item.com_reference is not None
    )
    return IndexEntry(
        initiative_id=initiative_id,
        short_title=_text(data.get("shortTitle")),
        reference=_text(data.get("reference")),
        com_references=tuple(references),
        publications=publications,
    )


def _search_page(
    fetcher: CachedFetcher, url: str, *, refresh: bool = False
) -> tuple[list[int], int | None, bool]:
    answer = _get_json(fetcher, url, refresh=refresh)
    page = _object(answer.get("initiativeResultDtoPage"), "initiative page")
    ids = [
        _required_integer(row.get("id"), "initiative id")
        for row in _objects(page.get("content"), "initiative list")
    ]
    return ids, _integer(page.get("totalElements")), page.get("last") is True


def crawl_index(
    fetcher: CachedFetcher,
    *,
    refresh: bool = False,
    progress: Progress | None = None,
    on_error: ErrorSink | None = None,
) -> Iterator[IndexEntry]:
    """Walk every initiative once: about 42 list pages plus one request per initiative.

    The list moves while it is being paged (new initiatives arrive at the top), so an
    initiative seen twice is fetched once. Without `on_error` the first failing
    initiative stops the crawl; with it, the failure is reported and the crawl goes on,
    so one broken record does not cost the other four thousand. `refresh` asks every
    page again instead of reading the cache, which is the only way to see initiatives
    and publications added since the cached crawl.
    """
    seen: set[int] = set()
    page = 0
    while True:
        ids, total, last = _search_page(fetcher, search_url(page=page), refresh=refresh)
        for initiative_id in ids:
            if initiative_id in seen:
                continue
            seen.add(initiative_id)
            try:
                entry = fetch_initiative(fetcher, initiative_id, refresh=refresh)
            except HysError as error:
                if on_error is None:
                    raise
                on_error(initiative_id, error)
            else:
                yield entry
            if progress is not None:
                progress(len(seen), total)
        if last or not ids:
            return
        page += 1


def write_index(path: Path, entries: Iterable[IndexEntry]) -> int:
    """JSON Lines, written atomically; returns the number of entries."""
    lines = [entry.model_dump_json() for entry in entries]
    write_bytes_atomic(path, "".join(f"{line}\n" for line in lines).encode("utf-8"))
    return len(lines)


def read_index(path: Path) -> Iterator[IndexEntry]:
    try:
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    yield IndexEntry.model_validate_json(line)
                except ValidationError as error:
                    raise HysError(f"{path}:{number} is not an index entry") from error
    except OSError as error:
        raise HysError(f"Cannot read the Have Your Say index at {path}") from error


def _wanted_reference(com_reference: str) -> str:
    wanted = normalise_com_reference(com_reference)
    if wanted is None:
        raise HysError(f"Not a COM reference: {com_reference!r}")
    return wanted


def find_initiatives(index: Iterable[IndexEntry], com_reference: str) -> tuple[IndexEntry, ...]:
    """Exact match on the normalised COM reference; a near match is not a match."""
    wanted = _wanted_reference(com_reference)
    return tuple(entry for entry in index if wanted in entry.com_references)


def find_by_title(fetcher: CachedFetcher, words: str, com_reference: str) -> tuple[IndexEntry, ...]:
    """Fallback before the index exists: search by title words, keep exact COM matches.

    The title search only proposes candidates (first page); the COM reference on a
    publication decides, so a similarly named initiative is never returned.
    """
    wanted = _wanted_reference(com_reference)
    ids, _, _ = _search_page(fetcher, search_url(page=0, size=TITLE_SEARCH_SIZE, text=words))
    entries = (fetch_initiative(fetcher, initiative_id) for initiative_id in dict.fromkeys(ids))
    return tuple(entry for entry in entries if wanted in entry.com_references)


# --- Feedback ---------------------------------------------------------------------------


def _attachments(raw: object) -> tuple[Attachment, ...]:
    found: list[Attachment] = []
    for item in _objects(raw, "attachments"):
        hys_document_id = _text(item.get("documentId"))
        if hys_document_id is None:
            # Without a document identifier there is nothing to download or cite.
            continue
        found.append(
            Attachment(
                attachment_id=_integer(item.get("id")),
                document_id=hys_document_id,
                file_name=_text(item.get("fileName")),
            )
        )
    return tuple(found)


def parse_feedback(raw: dict[str, object], publication_id: int) -> FeedbackItem:
    user_type = _text(raw.get("userType"))
    citizen = user_type in CITIZEN_USER_TYPES
    typed_id = None if citizen else _text(raw.get("trNumber"))
    found: list[str] = [] if typed_id is None else _REGISTER_ID.findall(typed_id)
    reference = _text(raw.get("referenceInitiative"))
    language = _text(raw.get("language"))
    feedback = raw.get("feedback")
    text = _clean(feedback) if isinstance(feedback, str) else ""
    translation = _text(raw.get("feedbackTextUserLanguage"))
    return FeedbackItem(
        feedback_id=_required_integer(raw.get("id"), "feedback id"),
        publication_id=publication_id,
        reference=reference,
        com_reference=normalise_com_reference(reference),
        submitted_at=parse_hys_datetime(raw.get("dateFeedback")),
        text=text,
        language=None if language is None else language.lower(),
        user_type=user_type,
        country=_text(raw.get("country")),
        company_size=_text(raw.get("companySize")),
        organization=None if citizen else _text(raw.get("organization")),
        # Two identifiers in one field name no single actor, so neither is taken.
        register_id=found[0] if len(found) == 1 else None,
        register_id_raw=typed_id,
        english_translation=(
            None if translation is None or translation == text.strip() else _clean(translation)
        ),
        attachments=_attachments(raw.get("attachments")),
    )


def iter_feedback(fetcher: CachedFetcher, publication_id: int) -> Iterator[FeedbackItem]:
    """Every feedback of one publication, page by page until the source says `last`.

    Pages are cached, so a consultation that is still open must be re-read with a fresh
    cache to see later submissions.
    """
    page = 0
    while True:
        url = feedback_url(publication_id, page)
        try:
            response = fetcher.get(url)
        except FetchError as error:
            if error.status == 400:
                raise HysUnavailable(
                    f"Publication {publication_id}: feedback is not served by the API"
                ) from error
            raise HysError(f"Have Your Say request failed: {error}") from error
        if response.body.strip() == b"bad_request":
            raise HysUnavailable(f"Publication {publication_id}: feedback is not served by the API")
        data = _decode(response.body, url)
        content = _objects(data.get("content"), "feedback page")
        for raw in content:
            yield parse_feedback(raw, publication_id)
        if data.get("last") is True or not content:
            return
        page += 1


# --- Atlas records ----------------------------------------------------------------------


def feedback_records(
    item: FeedbackItem, *, procedure_id: str | None, retrieved_at: datetime, url: str
) -> tuple[SourceDocument, DocumentText]:
    """The feedback's own text as a document; spans into it index `DocumentText.text`."""
    identifier = document_id("hys_feedback", str(item.feedback_id))
    document = SourceDocument(
        document_id=identifier,
        procedure_id=procedure_id,
        source_kind="hys_feedback",
        url=url,
        title=None if item.is_citizen else item.organization,
        published_at=item.submitted_at,
        retrieved_at=retrieved_at,
        sha256=hashlib.sha256(item.text.encode("utf-8")).hexdigest(),
        media_type="text/plain",
        language=item.language,
        extraction_status="extracted",
        extraction_method=FEEDBACK_METHOD,
        text_characters=len(item.text),
        reuse_terms=REUSE_TERMS,
    )
    return document, DocumentText(document_id=identifier, text=item.text)


def fetch_attachment(
    fetcher: CachedFetcher,
    attachment: Attachment,
    item: FeedbackItem,
    *,
    procedure_id: str | None,
) -> tuple[SourceDocument, DocumentText | None]:
    """Download one attachment and extract its text within the document service's limits.

    A PDF that cannot be read (scanned, encrypted, malformed, over the limits) still
    yields its `SourceDocument`, marked `failed` with the reason, and no text: it is
    counted, never dropped. Only a failed download raises, because then there are no
    bytes to describe.
    """
    url = download_url(attachment.document_id)
    try:
        response = fetcher.get(url)
    except FetchError as error:
        raise HysError(f"Attachment {attachment.document_id} not downloaded: {error}") from error
    identifier = document_id("hys_attachment", attachment.document_id)
    content_type = response.metadata.content_type
    text: str | None = None
    try:
        extracted = extract_document(response.body, "pdf")
    except DocumentExtractionError as error:
        status = "failed"
        method = f"{ATTACHMENT_METHOD}:{error.code}"
    else:
        text = _clean(PAGE_SEPARATOR.join(page.text for page in extracted.pages))
        complete = all(page.text.strip() for page in extracted.pages)
        status = "extracted" if complete else "partial"
        method = ATTACHMENT_METHOD
    document = SourceDocument(
        document_id=identifier,
        procedure_id=procedure_id,
        source_kind="hys_attachment",
        url=url,
        title=attachment.file_name,
        published_at=item.submitted_at,
        retrieved_at=response.metadata.fetched_at,
        sha256=hashlib.sha256(response.body).hexdigest(),
        media_type=None if content_type is None else content_type.split(";")[0].strip(),
        language=None,
        extraction_status=status,
        extraction_method=method,
        text_characters=None if text is None else len(text),
        reuse_terms=REUSE_TERMS,
    )
    return document, None if text is None else DocumentText(document_id=identifier, text=text)
