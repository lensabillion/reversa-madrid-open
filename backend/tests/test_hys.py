"""Have Your Say connector, checked offline against responses shaped like the real API."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import ContentStream, DecodedStreamObject, DictionaryObject, NameObject

from influence.extraction.cache import HttpCache
from influence.extraction.fetching import CachedFetcher, FetchError, RateLimiter, RawResponse
from influence.repositories.hys import (
    REUSE_TERMS,
    Attachment,
    FeedbackItem,
    HysError,
    HysUnavailable,
    IndexEntry,
    IndexFailure,
    Publication,
    com_references_in,
    crawl_index,
    download_url,
    failures_path,
    feedback_records,
    feedback_url,
    fetch_attachment,
    fetch_initiative,
    find_by_title,
    find_initiatives,
    initiative_url,
    iter_feedback,
    normalise_com_reference,
    parse_feedback,
    parse_hys_datetime,
    read_failures,
    read_index,
    search_url,
    write_failures,
    write_index,
)

FETCHED_AT = datetime(2026, 10, 3, 9, 30, tzinfo=UTC)
PROCEDURE = "2021/0106(COD)"
type Json = dict[str, object]


@dataclass
class ScriptedFetcher:
    """Answers from a script; an unscripted URL fails like a dead host would."""

    responses: dict[str, RawResponse]
    calls: list[str] = field(default_factory=list[str])

    def __call__(self, url: str, headers: Mapping[str, str] | None = None) -> RawResponse:
        self.calls.append(url)
        if url not in self.responses:
            raise FetchError(url, "No response: unscripted")
        return self.responses[url]


def as_json(value: object, status: int = 200) -> RawResponse:
    return RawResponse(status, "application/json", json.dumps(value).encode("utf-8"))


def make_fetcher(tmp_path: Path, responses: dict[str, RawResponse]) -> CachedFetcher:
    return CachedFetcher(
        cache=HttpCache(tmp_path / "cache"),
        fetcher=ScriptedFetcher(responses),
        limiter=RateLimiter(interval=0.0),
        clock=lambda: FETCHED_AT,
    )


def calls(fetcher: CachedFetcher) -> list[str]:
    scripted = fetcher.fetcher
    assert isinstance(scripted, ScriptedFetcher)
    return scripted.calls


def make_pdf(texts: tuple[str, ...]) -> bytes:
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
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        if text:
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
            page.replace_contents(ContentStream(stream, writer))
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def initiative(initiative_id: int, publications: list[Json]) -> Json:
    return {
        "id": initiative_id,
        "reference": "Ares(2020)3896535",
        "shortTitle": " Requirements for Artificial Intelligence ",
        "publications": publications,
    }


AI_PUBLICATIONS: list[Json] = [
    {
        "id": 25429,
        "type": "OPC_LAUNCHED",
        "reference": "AIConsult2020",
        "totalFeedback": 1216,
        "publishedDate": "2020/02/20 12:42:26",
        "adoptionDate": None,
        "endDate": "2020/06/14 00:00:00",
    },
    {
        "id": 14488,
        "type": "PROP_REG",
        "reference": "COM(2021)206",
        "totalFeedback": 304,
        "publishedDate": "2021/04/26 18:38:12",
        "adoptionDate": "2021/04/21 00:00:00",
        "endDate": "2021/08/06 23:59:59",
    },
    {"id": 14489, "type": "PROP_DIR", "reference": "COM(2021) 0206 final", "totalFeedback": None},
]


def search_page(ids: list[object], *, last: bool, total: int = 3) -> Json:
    return {
        "exactMatch": True,
        "initiativeResultDtoPage": {
            "content": [{"id": item, "shortTitle": "x"} for item in ids],
            "totalElements": total,
            "last": last,
        },
    }


def feedback(feedback_id: int, **changes: object) -> Json:
    record: Json = {
        "id": feedback_id,
        "referenceInitiative": "COM(2021)206",
        "dateFeedback": "2021/08/06 23:57:37",
        "feedback": "Equinet welcomes the proposal.",
        "language": "EN",
        "userType": "NGO",
        "country": "BEL",
        "companySize": "MICRO",
        "firstName": "Jeannette",
        "surname": "Example",
        "organization": "Equinet",
        "trNumber": "718971811339-46",
        "attachments": [
            {
                "id": 26041237,
                "fileName": "Equinet submission.docx",
                "ersFileName": "Equinet submission.pdf",
                "pages": None,
                "documentId": "090166e5e1cd1796",
                "size": 80083,
                "pdfSize": 634363,
            }
        ],
        "publicationId": 14488,
    }
    record.update(changes)
    return record


def feedback_page(records: list[Json], *, last: bool | None) -> Json:
    page: Json = {"content": records, "totalElements": len(records)}
    if last is not None:
        page["last"] = last
    return page


# --- Small readers ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("COM(2021)206", "COM(2021)206"),
        ("COM(2021) 0206 final", "COM(2021)206"),
        ("com/2020/825", "COM(2020)825"),
        ("COM(2022)0071", "COM(2022)71"),
        ("Ares(2020)3896535", None),
        ("TELECOM(2021)206", None),
        ("AIConsult2020", None),
        (None, None),
    ],
)
def test_com_references_are_normalised_or_unknown(raw: str | None, expected: str | None) -> None:
    assert normalise_com_reference(raw) == expected


def test_dates_are_brussels_local_time_and_unparseable_stays_unknown() -> None:
    summer = parse_hys_datetime("2021/08/06 23:57:37")
    winter = parse_hys_datetime(" 2021/01/06 10:00:00 ")
    assert summer is not None
    assert winter is not None
    assert summer.utcoffset() == timedelta(hours=2)
    assert winter.utcoffset() == timedelta(hours=1)
    assert summer.astimezone(UTC) == datetime(2021, 8, 6, 21, 57, 37, tzinfo=UTC)
    assert parse_hys_datetime("2021-08-06T23:57:37") is None
    assert parse_hys_datetime(None) is None


def test_urls_match_the_verified_endpoints() -> None:
    base = "https://ec.europa.eu/info/law/better-regulation"
    assert search_url(page=2) == f"{base}/brpapi/searchInitiatives?page=2&size=100&language=EN"
    assert search_url(page=0, size=20, text="artificial intelligence") == (
        f"{base}/brpapi/searchInitiatives?text=artificial%20intelligence&page=0&size=20&language=EN"
    )
    assert initiative_url(12527) == f"{base}/brpapi/groupInitiatives/12527?language=EN"
    assert feedback_url(14488, 3) == f"{base}/api/allFeedback?publicationId=14488&page=3&size=100"
    assert download_url("090166e5/x") == f"{base}/api/download/090166e5%2Fx"


# --- Index ------------------------------------------------------------------------------


def test_initiative_keeps_every_publication_and_its_com_reference(tmp_path: Path) -> None:
    fetcher = make_fetcher(
        tmp_path, {initiative_url(12527): as_json(initiative(12527, AI_PUBLICATIONS))}
    )
    entry = fetch_initiative(fetcher, 12527)
    assert entry.initiative_id == 12527
    assert entry.short_title == "Requirements for Artificial Intelligence"
    assert entry.reference == "Ares(2020)3896535"
    # Two publications carry the same COM number in different spellings: listed once.
    assert entry.com_references == ("COM(2021)206",)
    assert [item.publication_id for item in entry.publications] == [25429, 14488, 14489]
    consultation, proposal, directive = entry.publications
    assert (consultation.type, consultation.com_reference) == ("OPC_LAUNCHED", None)
    assert consultation.total_feedback == 1216
    assert consultation.adopted_at is None
    assert proposal.com_reference == "COM(2021)206"
    assert proposal.adopted_at == parse_hys_datetime("2021/04/21 00:00:00")
    assert proposal.feedback_end_at == parse_hys_datetime("2021/08/06 23:59:59")
    assert directive.total_feedback is None
    assert directive.published_at is None


@pytest.mark.parametrize(
    "body",
    [
        b"The groupId cannot be found!",
        b"[1, 2]",
        json.dumps({"publications": {"id": 1}}).encode(),
        json.dumps({"publications": ["x"]}).encode(),
        json.dumps({"publications": [{"id": "x"}]}).encode(),
        json.dumps({"publications": [{"id": True}]}).encode(),
        json.dumps({"publications": [{"id": 1.5}]}).encode(),
    ],
)
def test_malformed_initiative_is_a_typed_error(tmp_path: Path, body: bytes) -> None:
    fetcher = make_fetcher(tmp_path, {initiative_url(7): RawResponse(200, "text/plain", body)})
    with pytest.raises(HysError):
        fetch_initiative(fetcher, 7)


def test_initiative_without_publications_has_no_references(tmp_path: Path) -> None:
    fetcher = make_fetcher(tmp_path, {initiative_url(7): as_json({"id": 7, "shortTitle": " "})})
    assert fetch_initiative(fetcher, 7) == IndexEntry(
        initiative_id=7, short_title=None, reference=None, com_references=(), publications=()
    )


def ignore_error(initiative_id: int, error: HysError) -> None:
    del initiative_id, error


def crawl_responses() -> dict[str, RawResponse]:
    return {
        # The list endpoint writes identifiers as floats; 12527 repeats on the next page.
        search_url(page=0): as_json(search_page([12527.0, 404], last=False)),
        search_url(page=1): as_json(search_page([12527, 12417], last=True)),
        initiative_url(12527): as_json(initiative(12527, AI_PUBLICATIONS)),
        initiative_url(12417): as_json(
            initiative(12417, [{"id": 13971, "type": "PROP_REG", "reference": "COM(2020)825"}])
        ),
    }


def test_crawl_visits_each_initiative_once_and_reports_failures(tmp_path: Path) -> None:
    fetcher = make_fetcher(tmp_path, crawl_responses())
    progress: list[tuple[int, int | None]] = []
    errors: list[int] = []
    entries = list(
        crawl_index(
            fetcher,
            progress=lambda done, total: progress.append((done, total)),
            on_error=lambda initiative_id, _: errors.append(initiative_id),
        )
    )
    assert [entry.initiative_id for entry in entries] == [12527, 12417]
    assert errors == [404]
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert calls(fetcher).count(initiative_url(12527)) == 1
    # Resumable for free: a second crawl is answered from the cache, except the failure.
    before = len(calls(fetcher))
    assert len(list(crawl_index(fetcher, on_error=ignore_error))) == 2
    assert calls(fetcher)[before:] == [initiative_url(404)]


def test_crawl_without_error_sink_stops_at_the_first_failure(tmp_path: Path) -> None:
    fetcher = make_fetcher(tmp_path, crawl_responses())
    crawl = crawl_index(fetcher)
    assert next(crawl).initiative_id == 12527
    with pytest.raises(HysError, match="404"):
        next(crawl)


def test_crawl_stops_on_an_empty_page_even_without_last(tmp_path: Path) -> None:
    fetcher = make_fetcher(
        tmp_path,
        {
            search_url(page=0): as_json(search_page([12527], last=False)),
            search_url(page=1): as_json(search_page([], last=False)),
            initiative_url(12527): as_json(initiative(12527, AI_PUBLICATIONS)),
        },
    )
    assert [entry.initiative_id for entry in crawl_index(fetcher)] == [12527]


def test_index_round_trips_as_json_lines_and_finds_exact_references(tmp_path: Path) -> None:
    fetcher = make_fetcher(tmp_path, crawl_responses())
    entries = list(crawl_index(fetcher, on_error=ignore_error))
    path = tmp_path / "catalog" / "hys-index.jsonl"
    assert write_index(path, entries) == 2
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    path.write_text(path.read_text(encoding="utf-8") + "\n  \n", encoding="utf-8")
    loaded = list(read_index(path))
    assert loaded == entries
    assert [e.initiative_id for e in find_initiatives(loaded, "COM(2021) 0206 final")] == [12527]
    assert [e.initiative_id for e in find_initiatives(loaded, "COM(2020)825")] == [12417]
    # COM(2021)20 is a prefix of COM(2021)206 and must not match it.
    assert find_initiatives(loaded, "COM(2021)20") == ()
    with pytest.raises(HysError, match="Not a COM reference"):
        find_initiatives(loaded, "Ares(2020)3896535")


def test_unreadable_index_is_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(HysError, match="Cannot read"):
        list(read_index(tmp_path / "absent.jsonl"))
    broken = tmp_path / "broken.jsonl"
    broken.write_text('{"initiative_id": "x"}\n', encoding="utf-8")
    with pytest.raises(HysError, match=r"broken\.jsonl:1"):
        list(read_index(broken))


def test_title_search_keeps_only_initiatives_with_the_exact_reference(tmp_path: Path) -> None:
    url = search_url(page=0, size=20, text="artificial intelligence")
    fetcher = make_fetcher(
        tmp_path,
        {
            url: as_json(search_page([12270.0, 12527.0, 12527.0], last=True)),
            initiative_url(12270): as_json(
                initiative(12270, [{"id": 1, "type": "OPC_LAUNCHED", "reference": "AIConsult2020"}])
            ),
            initiative_url(12527): as_json(initiative(12527, AI_PUBLICATIONS)),
        },
    )
    found = find_by_title(fetcher, "artificial intelligence", "COM(2021)206")
    assert [entry.initiative_id for entry in found] == [12527]
    assert calls(fetcher).count(initiative_url(12527)) == 1
    with pytest.raises(HysError, match="Not a COM reference"):
        find_by_title(fetcher, "artificial intelligence", "206")


# --- Feedback ---------------------------------------------------------------------------


def test_feedback_keeps_actor_fields_and_never_personal_names() -> None:
    item = parse_feedback(feedback(2665651), 14488)
    assert item == FeedbackItem(
        feedback_id=2665651,
        publication_id=14488,
        reference="COM(2021)206",
        com_reference="COM(2021)206",
        submitted_at=parse_hys_datetime("2021/08/06 23:57:37"),
        text="Equinet welcomes the proposal.",
        language="en",
        user_type="NGO",
        country="BEL",
        company_size="MICRO",
        organization="Equinet",
        register_id="718971811339-46",
        register_id_raw="718971811339-46",
        english_translation=None,
        attachments=(
            Attachment(
                attachment_id=26041237,
                document_id="090166e5e1cd1796",
                file_name="Equinet submission.docx",
            ),
        ),
    )
    assert not item.is_citizen
    dumped = item.model_dump_json()
    assert "Jeannette" not in dumped
    assert "Example" not in dumped
    assert "firstName" not in FeedbackItem.model_fields
    assert "surname" not in FeedbackItem.model_fields


def test_citizen_feedback_drops_everything_that_could_name_the_person() -> None:
    item = parse_feedback(
        feedback(1, userType="EU_CITIZEN", organization="Jeannette Example", trNumber="123456-78"),
        14488,
    )
    assert item.is_citizen
    assert item.organization is None
    assert item.register_id is None
    assert item.register_id_raw is None


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("TR 435520331024-09", "435520331024-09"),
        ("\u200b135037514504-30", "135037514504-30"),
        ("397482431021-09.", "397482431021-09"),
        ("535 183 0264 - 31", None),
        ("840667012559", None),
        ("No", None),
        ("435520331024-09 and 135037514504-30", None),
        ("435520331024-091", None),
        ("", None),
        (None, None),
    ],
)
def test_register_id_is_read_only_when_well_formed(typed: str | None, expected: str | None) -> None:
    item = parse_feedback(feedback(1, trNumber=typed), 14488)
    assert item.register_id == expected
    assert item.register_id_raw == (typed.strip() or None if typed else None)


def test_questionnaire_shaped_feedback_keeps_unknowns_unknown() -> None:
    # The DSA consultation (publication 13127) serves records with no text or user type.
    raw: Json = {
        "id": 552505,
        "referenceInitiative": "Digital_Services_Act",
        "dateFeedback": "not a date",
        "trNumber": "",
        "organization": "",
        "attachments": [{"id": 1, "fileName": "no-document.pdf"}],
    }
    item = parse_feedback(raw, 13127)
    assert item.text == ""
    assert item.submitted_at is None
    assert item.com_reference is None
    assert item.reference == "Digital_Services_Act"
    assert (item.language, item.user_type, item.organization, item.country) == (
        None,
        None,
        None,
        None,
    )
    assert item.attachments == ()
    assert parse_feedback({"id": 2, "attachments": None}, 13127).attachments == ()


def test_translation_is_kept_apart_from_the_original_text() -> None:
    original = "Selon Le Groupe La Poste \ud83d"
    translated = parse_feedback(
        feedback(
            1, language="FR", feedback=original, feedbackTextUserLanguage="According to \ud83d"
        ),
        14488,
    )
    # A lone surrogate cannot be written as UTF-8; it is replaced, never dropped silently.
    assert translated.text == "Selon Le Groupe La Poste \ufffd"
    assert translated.english_translation == "According to \ufffd"
    assert translated.language == "fr"
    same = parse_feedback(feedback(2, feedback="Same. ", feedbackTextUserLanguage="Same."), 14488)
    assert same.english_translation is None


def test_feedback_pages_are_read_until_last(tmp_path: Path) -> None:
    fetcher = make_fetcher(
        tmp_path,
        {
            feedback_url(14488, 0): as_json(feedback_page([feedback(3), feedback(2)], last=False)),
            feedback_url(14488, 1): as_json(feedback_page([feedback(1)], last=True)),
        },
    )
    assert [item.feedback_id for item in iter_feedback(fetcher, 14488)] == [3, 2, 1]
    assert calls(fetcher) == [feedback_url(14488, 0), feedback_url(14488, 1)]


def test_feedback_paging_ends_on_an_empty_page_without_last(tmp_path: Path) -> None:
    fetcher = make_fetcher(
        tmp_path,
        {
            feedback_url(5, 0): as_json(feedback_page([feedback(3)], last=None)),
            feedback_url(5, 1): as_json(feedback_page([], last=None)),
        },
    )
    assert [item.feedback_id for item in iter_feedback(fetcher, 5)] == [3]


def test_unserved_questionnaire_is_a_typed_gap_not_a_crash(tmp_path: Path) -> None:
    fetcher = make_fetcher(
        tmp_path,
        {
            feedback_url(25429, 0): RawResponse(400, "text/plain;charset=UTF-8", b"bad_request"),
            feedback_url(25430, 0): RawResponse(200, "text/plain", b"bad_request\n"),
            feedback_url(25431, 0): RawResponse(503, "text/plain", b"down"),
            feedback_url(25432, 0): RawResponse(200, "text/html", b"<html>"),
        },
    )
    for publication in (25429, 25430):
        with pytest.raises(HysUnavailable, match=str(publication)):
            list(iter_feedback(fetcher, publication))
    for publication in (25431, 25432):
        with pytest.raises(HysError) as error:
            list(iter_feedback(fetcher, publication))
        assert not isinstance(error.value, HysUnavailable)


# --- Atlas records ----------------------------------------------------------------------


def test_feedback_becomes_a_source_document_and_its_text() -> None:
    item = parse_feedback(feedback(2665651, language="FR", feedback="Caf\u00e9 d'abord."), 14488)
    url = feedback_url(14488, 0)
    document, text = feedback_records(
        item, procedure_id=PROCEDURE, retrieved_at=FETCHED_AT, url=url
    )
    assert document.document_id == "doc:hys_feedback:2665651"
    assert text.document_id == document.document_id
    assert text.text == "Caf\u00e9 d'abord."
    assert document.source_kind == "hys_feedback"
    assert document.procedure_id == PROCEDURE
    assert document.url == url
    assert document.title == "Equinet"
    assert document.published_at == item.submitted_at
    assert document.retrieved_at == FETCHED_AT
    assert document.sha256 == hashlib.sha256("Caf\u00e9 d'abord.".encode()).hexdigest()
    assert document.language == "fr"
    assert document.extraction_status == "extracted"
    assert document.text_characters == 13
    assert document.reuse_terms == REUSE_TERMS

    citizen = parse_feedback(feedback(9, userType="NON_EU_CITIZEN", dateFeedback=None), 14488)
    anonymous, _ = feedback_records(citizen, procedure_id=None, retrieved_at=FETCHED_AT, url=url)
    assert anonymous.title is None
    assert anonymous.published_at is None
    assert anonymous.procedure_id is None


def test_attachment_text_is_extracted_and_hashed_from_the_pdf_bytes(tmp_path: Path) -> None:
    item = parse_feedback(feedback(2665651), 14488)
    attachment = item.attachments[0]
    body = make_pdf(("Article 5 shall not apply.", "Delete Article 6."))
    url = download_url(attachment.document_id)
    fetcher = make_fetcher(tmp_path, {url: RawResponse(200, "application/pdf;charset=UTF-8", body)})
    document, text = fetch_attachment(fetcher, attachment, item, procedure_id=PROCEDURE)
    assert text is not None
    assert text.text == "Article 5 shall not apply.\n\nDelete Article 6."
    assert text.document_id == document.document_id == "doc:hys_attachment:090166e5e1cd1796"
    assert document.source_kind == "hys_attachment"
    assert document.url == url
    assert document.title == "Equinet submission.docx"
    assert document.sha256 == hashlib.sha256(body).hexdigest()
    assert document.media_type == "application/pdf"
    assert document.extraction_status == "extracted"
    assert document.extraction_method == "pypdf"
    assert document.text_characters == len(text.text)
    assert document.published_at == item.submitted_at
    assert document.retrieved_at == FETCHED_AT
    assert document.language is None
    assert document.reuse_terms == REUSE_TERMS


def test_pdf_with_a_blank_page_is_partial(tmp_path: Path) -> None:
    item = parse_feedback(feedback(1), 14488)
    attachment = item.attachments[0]
    fetcher = make_fetcher(
        tmp_path,
        {
            download_url(attachment.document_id): RawResponse(
                200, None, make_pdf(("Only this page has text.", ""))
            )
        },
    )
    document, text = fetch_attachment(fetcher, attachment, item, procedure_id=PROCEDURE)
    assert document.extraction_status == "partial"
    assert document.media_type is None
    assert text is not None
    assert text.text == "Only this page has text.\n\n"


@pytest.mark.parametrize(
    ("body", "code"),
    [(make_pdf(("",)), "ocr_required"), (b"PK\x03\x04 not a pdf", "invalid_pdf")],
)
def test_unreadable_attachment_is_counted_as_failed_not_dropped(
    tmp_path: Path, body: bytes, code: str
) -> None:
    item = parse_feedback(feedback(1), 14488)
    attachment = item.attachments[0]
    fetcher = make_fetcher(
        tmp_path, {download_url(attachment.document_id): RawResponse(200, "application/pdf", body)}
    )
    document, text = fetch_attachment(fetcher, attachment, item, procedure_id=PROCEDURE)
    assert text is None
    assert document.extraction_status == "failed"
    assert document.extraction_method == f"pypdf:{code}"
    assert document.text_characters is None
    assert document.sha256 == hashlib.sha256(body).hexdigest()


def test_attachment_that_cannot_be_downloaded_is_a_typed_error(tmp_path: Path) -> None:
    item = parse_feedback(feedback(1), 14488)
    with pytest.raises(HysError, match="090166e5e1cd1796 not downloaded"):
        fetch_attachment(make_fetcher(tmp_path, {}), item.attachments[0], item, procedure_id=None)


def test_a_citizens_attachment_never_publishes_its_file_name(tmp_path: Path) -> None:
    named = [{"id": 1, "fileName": "Letter from Jeannette Example.pdf", "documentId": "D1"}]
    citizen = feedback(
        9, userType="EU_CITIZEN", organization=None, trNumber=None, attachments=named
    )
    item = parse_feedback(citizen, 14488)
    body = make_pdf(("I support the proposal.",))
    fetcher = make_fetcher(
        tmp_path, {download_url("D1"): RawResponse(200, "application/pdf", body)}
    )

    document, text = fetch_attachment(fetcher, item.attachments[0], item, procedure_id=PROCEDURE)

    assert document.title is None
    assert text is not None


def test_refresh_asks_the_feedback_and_the_attachment_again(tmp_path: Path) -> None:
    item = parse_feedback(feedback(1), 14488)
    attachment = item.attachments[0]
    page = feedback_url(14488, 0)
    download = download_url(attachment.document_id)
    fetcher = make_fetcher(
        tmp_path,
        {
            page: as_json(feedback_page([feedback(1)], last=True)),
            download: RawResponse(200, "application/pdf", make_pdf(("Text.",))),
        },
    )
    for refresh in (False, False, True):
        list(iter_feedback(fetcher, 14488, refresh=refresh))
        fetch_attachment(fetcher, attachment, item, procedure_id=PROCEDURE, refresh=refresh)

    # Once from the source, once from the cache, and once more because of the refresh.
    assert calls(fetcher) == [page, download, page, download]


def test_every_com_reference_of_a_package_publication_finds_its_initiative() -> None:
    package = "COM(2020)0825 and COM(2020)842 final"
    assert com_references_in(package) == ("COM(2020)825", "COM(2020)842")
    assert com_references_in("COM(2020)825; COM(2020)825") == ("COM(2020)825",)
    assert com_references_in(None) == ()
    assert normalise_com_reference(package) == "COM(2020)825"
    publication = Publication(
        publication_id=1,
        type="PROP_REG",
        reference=package,
        com_reference="COM(2020)825",
        total_feedback=None,
        published_at=None,
        adopted_at=None,
        feedback_end_at=None,
    )
    # As an index built before every reference was kept: only the first one is listed.
    entry = IndexEntry(
        initiative_id=1,
        short_title=None,
        reference=None,
        com_references=("COM(2020)825",),
        publications=(publication,),
    )
    assert find_initiatives([entry], "COM(2020)842") == (entry,)
    assert find_initiatives([entry], "COM(2020)825") == (entry,)
    assert find_initiatives([entry], "COM(2020)900") == ()


def test_crawled_initiative_lists_every_reference_of_its_publications(tmp_path: Path) -> None:
    raw = initiative(7, [{"id": 2, "type": "PROP_REG", "reference": "COM(2020)825, COM(2020)842"}])
    fetcher = make_fetcher(tmp_path, {initiative_url(7): as_json(raw)})
    assert fetch_initiative(fetcher, 7).com_references == ("COM(2020)825", "COM(2020)842")


def test_failed_initiatives_round_trip_beside_the_index(tmp_path: Path) -> None:
    index = tmp_path / "hys-index.jsonl"
    path = failures_path(index)
    assert path == tmp_path / "hys-index.failed.jsonl"
    assert read_failures(path) == ()
    failures = (IndexFailure(initiative_id=404, error="HTTP 404"),)
    assert write_failures(path, failures) == 1
    assert read_failures(path) == failures
    path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(HysError, match="failed initiatives"):
        read_failures(path)


def test_a_recoverable_pdf_is_read_rather_than_rejected(tmp_path: Path) -> None:
    pdf = make_pdf(("We ask for a notice period of at least six months.",))
    offset = pdf.rindex(b"startxref") + len(b"startxref\n")
    end = pdf.index(b"\n", offset)
    # An xref offset a few bytes off, as incremental saves and editors leave it.
    shifted = pdf[:offset] + str(int(pdf[offset:end]) + 3).encode() + pdf[end:]
    item = parse_feedback(feedback(1), 14488)
    attachment = item.attachments[0]
    fetcher = make_fetcher(
        tmp_path,
        {download_url(attachment.document_id): RawResponse(200, "application/pdf", shifted)},
    )

    document, text = fetch_attachment(fetcher, attachment, item, procedure_id=PROCEDURE)

    assert document.extraction_status == "extracted"
    assert text is not None
    assert text.text == "We ask for a notice period of at least six months."
