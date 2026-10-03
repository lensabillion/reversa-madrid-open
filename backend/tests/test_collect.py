"""The collect pipeline end to end, offline: tiny inputs shaped like the real sources.

Every test builds its own data root under `tmp_path` (Parltrack dumps, a register export,
a Have Your Say index) and answers HTTP from a script, so nothing reads `data/` or the
network. The clock and the stage timer are counters, so manifests are repeatable.
"""

import hashlib
import itertools
import json
import urllib.parse
from collections.abc import Mapping, Sequence
from compression import zstd
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import ContentStream, DecodedStreamObject, DictionaryObject, NameObject

from influence.extraction.cache import HttpCache
from influence.extraction.fetching import CachedFetcher, FetchError, RateLimiter, RawResponse
from influence.extraction.records import RECEIPT_NAME, StageStore
from influence.repositories import cellar, hys
from influence.schemas.atlas import (
    CITIZENS_ACTOR_ID,
    Actor,
    Amendment,
    ArticleVersion,
    DocumentText,
    LayerCoverage,
    Passage,
    SourceDocument,
    StageReceipt,
    span_matches,
)
from influence.services.actors import CITIZENS_NAME
from influence.services.collect import (
    ALIASES,
    NO_COM_REFERENCE,
    NO_CONNECTOR,
    OPEN_PROCEDURE,
    POSITION_NOT_COLLECTED,
    REGISTER_UNAVAILABLE,
    CollectError,
    CollectResult,
    bundle_path,
    catalog_path,
    collect_law,
    dump_path,
    hys_index_path,
    load_catalog,
    read_stage_records,
    register_path,
    resolve_procedure,
)
from influence.services.law_query import parse_query

T0 = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
AI_ACT = "2021/0106(COD)"
OPEN = "2025/0059(COD)"
BARE = "2030/0009(COD)"
type Json = dict[str, object]
type Answer = RawResponse | FetchError

# --- Sources ------------------------------------------------------------------------------


def dossier(
    reference: str,
    title: str,
    stage: str = "Procedure completed",
    *,
    com: str | None = None,
    celex: str | None = None,
) -> Json:
    procedure: Json = {"reference": reference, "title": title, "stage_reached": stage}
    if celex is not None:
        procedure["final"] = {"url": f"https://eur-lex.europa.eu/x?lg=EN&numdoc={celex}"}
    documents = [] if com is None else [{"title": com}]
    events: list[Json] = [
        {
            "date": "2021-04-21T00:00:00",
            "type": "Legislative proposal published",
            "docs": documents,
        },
        {"date": "2024-07-12T00:00:00", "type": "Final act published in Official Journal"},
    ]
    return {"procedure": procedure, "events": events}


DOSSIERS: tuple[Json, ...] = (
    dossier(AI_ACT, "Artificial Intelligence Act", com="COM(2021)0206", celex="32024R1689"),
    dossier(OPEN, "Space Safety Rules", "Awaiting committee decision", com="COM(2025)0100"),
    dossier(BARE, "Empty Law"),
    dossier("2030/0001(COD)", "Widget Safety", com="COM(2030)0005"),
    dossier("2030/0002(COD)", "Widget Safety", com="COM(2030)0005"),
)


def amendment(reference: str, source_id: str, meps: Sequence[int] = (197721, 125042)) -> Json:
    return {
        "peid": "PE704.585v01-00",
        "reference": reference,
        "date": "2022-01-25T00:00:00",
        "committee": ["ENVI"],
        "seq": 68,
        "id": source_id,
        "orig_lang": "EN",
        "old": ["Providers may publish audits."],
        "new": ["Providers shall publish audits."],
        "authors": "César Luena, Margrete Auken",
        "meps": list(meps),
        "location": [["Proposal for a regulation", "Article 1"]],
    }


def member(mep_id: int, name: str) -> Json:
    return {
        "UserID": mep_id,
        "Name": {"full": name},
        "Groups": [{"groupid": "S&D", "start": "2019-07-02T00:00:00", "end": "9999-12-31"}],
        "Constituencies": [{"country": "Spain", "start": "2019-07-02T00:00:00"}],
    }


MEMBERS: tuple[Json, ...] = (member(197721, "César LUENA"), member(125042, "Margrete AUKEN"))

REGISTER = (
    "<?xml version='1.1' encoding='UTF-8'?>\n"
    '<ListOfIRPublicDetail xmlns="http://intragate.ec.europa.eu/transparencyregister/odp">\n'
    '  <resultList xmlns="">\n'
    "    <interestRepresentative>\n"
    "      <identificationCode>718971811339-46</identificationCode>\n"
    "      <name>\n        <originalName>Equinet</originalName>\n      </name>\n"
    "      <headOffice>\n        <country>BELGIUM</country>\n      </headOffice>\n"
    "    </interestRepresentative>\n"
    "  </resultList>\n"
    "</ListOfIRPublicDetail>\n"
)


def publication(publication_id: int, reference: str | None) -> hys.Publication:
    return hys.Publication(
        publication_id=publication_id,
        type="PROP_REG",
        reference=reference,
        com_reference=hys.normalise_com_reference(reference),
        total_feedback=None,
        published_at=None,
        adopted_at=None,
        feedback_end_at=None,
    )


AI_INITIATIVE = hys.IndexEntry(
    initiative_id=12527,
    short_title="Requirements for Artificial Intelligence",
    reference="Ares(2020)3896535",
    com_references=("COM(2021)206",),
    publications=(publication(25429, "AIConsult2020"), publication(14488, "COM(2021)206")),
)
OTHER_INITIATIVE = hys.IndexEntry(
    initiative_id=1,
    short_title="Something else",
    reference=None,
    com_references=("COM(2019)1",),
    publications=(publication(5, "COM(2019)1"),),
)


def write_dump(path: Path, records: Sequence[Json]) -> None:
    """One record per line: `[` opens the first, `,` every later one, `]` ends the file."""
    lines = [
        ("[" if index == 0 else ",") + json.dumps(record) for index, record in enumerate(records)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(zstd.compress("".join(f"{line}\n" for line in [*lines, "]"]).encode()))


def build_world(
    root: Path,
    *,
    dossiers: Sequence[Json] | None = DOSSIERS,
    committee: Sequence[Json] | None = (amendment(AI_ACT, "PE704.585-68"),),
    plenary: Sequence[Json] | None = (amendment(AI_ACT, "A9-0188/2023-1", (197721,)),),
    members: Sequence[Json] | None = MEMBERS,
    register: str | None = REGISTER,
    index: Sequence[hys.IndexEntry] | None = (OTHER_INITIATIVE, AI_INITIATIVE),
) -> Path:
    """A data root holding the given sources; None leaves that source out entirely."""
    dumps = (
        ("ep_dossiers", dossiers),
        ("ep_amendments", committee),
        ("ep_plenary_amendments", plenary),
        ("ep_meps", members),
    )
    for name, records in dumps:
        if records is not None:
            write_dump(dump_path(root, name), records)
    if register is not None:
        register_path(root).parent.mkdir(parents=True, exist_ok=True)
        register_path(root).write_text(register, encoding="utf-8")
    if index is not None:
        hys.write_index(hys_index_path(root), index)
    return root


# --- HTTP ---------------------------------------------------------------------------------


@dataclass
class ScriptedFetcher:
    """Answers the first script entry whose text occurs in the decoded URL.

    SPARQL queries travel URL-encoded, so the script names a fragment of the address. A
    scripted `FetchError` is raised; an unscripted URL is a host that does not answer.
    """

    script: Mapping[str, Answer]
    calls: list[str] = field(default_factory=list[str])

    def __call__(self, url: str, headers: Mapping[str, str] | None = None) -> RawResponse:
        del headers
        decoded = urllib.parse.unquote_plus(url)
        self.calls.append(decoded)
        for fragment, answer in self.script.items():
            if fragment in decoded:
                if isinstance(answer, FetchError):
                    raise answer
                return answer
        raise FetchError(url, "No response: unscripted")


def as_json(value: object) -> RawResponse:
    return RawResponse(200, "application/json", json.dumps(value).encode())


def sparql(*rows: dict[str, str]) -> RawResponse:
    bindings = [{name: {"value": value} for name, value in row.items()} for row in rows]
    return as_json({"results": {"bindings": bindings}})


def xhtml(body: str) -> RawResponse:
    page = f"<html><body>{body}</body></html>".encode()
    return RawResponse(200, "application/xhtml+xml;charset=UTF-8", page)


def make_pdf(text: str) -> RawResponse:
    writer = PdfWriter()
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
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
    page.replace_contents(ContentStream(stream, writer))
    output = BytesIO()
    writer.write(output)
    return RawResponse(200, "application/pdf", output.getvalue())


def feedback(feedback_id: int, **changes: object) -> Json:
    record: Json = {
        "id": feedback_id,
        "referenceInitiative": "COM(2021)206",
        "dateFeedback": "2021/08/06 23:57:37",
        "feedback": "Equinet welcomes the proposal. Article 5 should be stricter.",
        "language": "EN",
        "userType": "NGO",
        "country": "BEL",
        "firstName": "Jeannette",
        "surname": "Example",
        "organization": "Equinet",
        "trNumber": "718971811339-46",
        "attachments": [],
    }
    record.update(changes)
    return record


def attached(hys_document_id: str, file_name: str) -> list[Json]:
    return [{"id": 1, "fileName": file_name, "documentId": hys_document_id}]


def page(*items: Json) -> RawResponse:
    return as_json({"content": list(items), "last": True})


FEEDBACK = page(
    feedback(1, attachments=attached("att-ngo", "Equinet submission.pdf")),
    feedback(
        2,
        userType="EU_CITIZEN",
        organization=None,
        trNumber=None,
        firstName="Jane",
        surname="Secret",
        feedback="I worry about surveillance.",
        attachments=attached("att-citizen", "Jane Secret letter.pdf"),
    ),
    feedback(
        3,
        userType="COMPANY",
        organization="Acme Robotics",
        trNumber=None,
        feedback="",
        attachments=attached("att-broken", "scan.pdf"),
    ),
)
FINAL_ACT = xhtml(
    '<p class="oj-hd-date">12.7.2024</p>'
    '<div id="rct_1"><p>(1) Recital text one.</p></div>'
    '<div id="art_1"><p class="oj-ti-art">Article 1</p>'
    "<p>1.   Providers shall publish audits.</p></div>"
)
PROPOSAL = xhtml(
    "<p>Whereas:</p><p>(1) The purpose is safety.</p><p>HAVE ADOPTED THIS REGULATION:</p>"
    "<p>Article 1</p><p>Providers may publish audits.</p><p>Done at Brussels,</p>"
)
LISTING = RawResponse(
    300,
    "text/html",
    b'<a href="http://publications.europa.eu/resource/cellar/e06.0001.03/DOC_1">DOC_1</a>'
    b'<li title="stream_name">1_EN_ACT_part1_v7.html</li><li title="stream_order">1</li>',
)
UNAVAILABLE = RawResponse(200, "text/plain", b"bad_request")
SCRIPT: Mapping[str, Answer] = {
    "dossier_produces_resource_legal": sparql({"final": "32024R1689", "prop": "52021PC0206"}),
    "resource/celex/32024R1689": FINAL_ACT,
    "resource/celex/52021PC0206": LISTING,
    "DOC_1": PROPOSAL,
    "publicationId=25429": UNAVAILABLE,
    "publicationId=14488": FEEDBACK,
    "download/att-ngo": make_pdf("Providers must publish audits."),
    "download/att-citizen": make_pdf("My name is Jane Secret."),
    "download/att-broken": RawResponse(200, "application/pdf", b"not a pdf"),
}


def make_fetcher(root: Path, script: Mapping[str, Answer] = SCRIPT) -> CachedFetcher:
    return CachedFetcher(
        cache=HttpCache(root / "cache"),
        fetcher=ScriptedFetcher(script),
        limiter=RateLimiter(interval=0.0),
        clock=lambda: T0,
    )


def calls(fetcher: CachedFetcher) -> list[str]:
    scripted = fetcher.fetcher
    assert isinstance(scripted, ScriptedFetcher)
    return scripted.calls


def run(
    root: Path,
    fetcher: CachedFetcher,
    query: str = AI_ACT,
    *,
    attachment_limit: int | None = None,
    messages: list[str] | None = None,
) -> CollectResult:
    ticks = itertools.count()
    seconds = itertools.count()
    if messages is None:
        return collect_law(
            query,
            data_root=root,
            fetcher=fetcher,
            clock=lambda: T0 + timedelta(seconds=next(ticks)),
            code_revision="test-1",
            attachment_limit=attachment_limit,
            hardware="test bench",
            timer=lambda: float(next(seconds)),
        )
    return collect_law(
        query,
        data_root=root,
        fetcher=fetcher,
        clock=lambda: T0 + timedelta(seconds=next(ticks)),
        code_revision="test-1",
        attachment_limit=attachment_limit,
        timer=lambda: float(next(seconds)),
        progress=messages.append,
    )


def layers(result: CollectResult) -> dict[str, LayerCoverage]:
    return {row.layer: row for row in result.law.coverage}


def stages(result: CollectResult) -> dict[str, StageReceipt]:
    return {receipt.stage: receipt for receipt in result.manifest.stages}


def records[T: (SourceDocument, DocumentText, Passage, Actor, Amendment, ArticleVersion)](
    result: CollectResult, stage: str, name: str, model: type[T]
) -> tuple[T, ...]:
    return read_stage_records(result.bundle, stages(result)[stage], name, model)


# --- The whole pipeline -------------------------------------------------------------------


def test_a_common_name_becomes_the_law_record_with_every_layer_labelled(tmp_path: Path) -> None:
    root = build_world(tmp_path)
    result = run(root, make_fetcher(root), "AI Act")

    law = result.law
    assert (law.procedure_id, law.title, law.status) == (
        AI_ACT,
        "Artificial Intelligence Act",
        "completed",
    )
    assert (law.celex_proposal, law.celex_final, law.com_reference) == (
        "52021PC0206",
        "32024R1689",
        "COM(2021)206",
    )
    assert (law.proposed_on, law.completed_on) == (date(2021, 4, 21), date(2024, 7, 12))
    coverage = layers(result)
    assert list(coverage) == [
        "metadata",
        "proposal",
        "parliament_position",
        "final_act",
        "committee_amendments",
        "plenary_amendments",
        "asks",
        "actors",
        "meetings",
        "votes",
    ]
    assert {name: (row.status, row.count) for name, row in coverage.items()} == {
        "metadata": ("complete", None),
        "proposal": ("complete", 2),
        "parliament_position": ("not_collected", None),
        "final_act": ("complete", 2),
        "committee_amendments": ("complete", 1),
        "plenary_amendments": ("complete", 1),
        "asks": ("partial", 3),
        "actors": ("complete", 5),
        "meetings": ("not_collected", None),
        "votes": ("not_collected", None),
    }
    assert coverage["parliament_position"].reason == POSITION_NOT_COLLECTED
    assert coverage["votes"].reason == NO_CONNECTOR
    assert coverage["final_act"].source_updated_on == date(2024, 7, 12)
    assert coverage["proposal"].source_updated_on == date(2021, 4, 21)
    assert coverage["asks"].reason == (
        "Publication 25429: feedback is not served by the API; "
        "1 of 3 feedback items carry no text; "
        "1 attachments have no extractable text"
    )

    manifest = result.manifest
    assert manifest == StageStore(result.bundle).current()
    assert result.manifest_path == bundle_path(root, AI_ACT) / "manifest.json"
    assert result.bundle == root / "laws" / "2021-0106-COD"
    assert (manifest.status, manifest.query, manifest.procedure_id) == (
        "complete",
        "AI Act",
        AI_ACT,
    )
    assert manifest.run_id == "2021-0106-COD-20261003T150000Z"
    assert (manifest.started_at, manifest.completed_at) == (T0, T0 + timedelta(seconds=1))
    assert (manifest.code_revision, manifest.hardware) == ("test-1", "test bench")
    assert manifest.config == {"attachment_limit": "all"}
    assert manifest.coverage == law.coverage
    assert [(stage.stage, stage.status, stage.seconds) for stage in manifest.stages] == [
        ("metadata", "complete", 1.0),
        ("law_texts", "complete", 1.0),
        ("amendments", "complete", 1.0),
        ("asks", "complete", 1.0),
        ("actors", "complete", 1.0),
    ]
    assert all(not stage.errors for stage in manifest.stages)
    assert stages(result)["asks"].counts == {
        "initiatives_from_index": 1,
        "publications": 2,
        "publications_unavailable": 1,
        "feedback": 3,
        "feedback_without_text": 1,
        "feedback_with_register_id": 1,
        "feedback_from_citizens": 1,
        "feedback_with_attachments": 3,
        "publication_14488_feedback": 3,
        "publication_14488_with_register_id": 1,
        "publication_14488_with_attachments": 3,
        "attachments_listed": 3,
        "attachments_read": 3,
        "attachments_failed_download": 0,
        "attachments_without_text": 1,
        "passages": 4,
        "register_entries": 1,
    }
    assert stages(result)["amendments"].counts == {"committee": 1, "plenary": 1}
    assert stages(result)["law_texts"].counts == {
        "proposal_provisions": 2,
        "final_act_provisions": 2,
    }
    assert stages(result)["actors"].counts["amendment_authors"] == 2
    assert stages(result)["actors"].counts["members_found"] == 2
    assert stages(result)["actors"].counts["register_id"] == 1
    assert stages(result)["actors"].counts["citizens"] == 1


def test_the_records_join_and_every_passage_quotes_its_document_exactly(tmp_path: Path) -> None:
    root = build_world(tmp_path)
    result = run(root, make_fetcher(root))

    acts = {
        item.document_id: item
        for item in records(result, "law_texts", "documents.jsonl", SourceDocument)
    }
    final, proposal = acts["doc:cellar:32024R1689"], acts["doc:cellar:52021PC0206"]
    # CELLAR's three-letter code is normalised to the two letters every other source uses.
    assert (final.language, proposal.language) == ("en", "en")
    assert final.published_at == datetime(2024, 7, 12, tzinfo=UTC)
    assert proposal.published_at == datetime(2021, 4, 21, tzinfo=UTC)
    assert proposal.url.endswith("/DOC_1")
    articles = records(result, "law_texts", "articles.jsonl", ArticleVersion)
    assert [(item.stage, item.provision) for item in articles] == [
        ("proposal", "Recital 1"),
        ("proposal", "Article 1"),
        ("final_act", "Recital 1"),
        ("final_act", "Article 1(1)"),
    ]
    assert {item.version_date for item in articles} == {date(2021, 4, 21), date(2024, 7, 12)}

    tabled = records(result, "amendments", "amendments.jsonl", Amendment)
    assert [(item.stage, item.procedure_id) for item in tabled] == [
        ("committee", AI_ACT),
        ("plenary", AI_ACT),
    ]
    dumps = records(result, "amendments", "documents.jsonl", SourceDocument)
    assert [item.document_id for item in dumps] == [
        "doc:parltrack:ep_amendments",
        "doc:parltrack:ep_plenary_amendments",
    ]
    committee_dump = dump_path(root, "ep_amendments")
    assert dumps[0].sha256 == hashlib.sha256(committee_dump.read_bytes()).hexdigest()
    assert dumps[0].retrieved_at == datetime.fromtimestamp(committee_dump.stat().st_mtime, UTC)

    documents = {
        item.document_id: item
        for item in records(result, "asks", "documents.jsonl", SourceDocument)
    }
    assert list(documents) == [
        "doc:hys_feedback:1",
        "doc:hys_feedback:2",
        "doc:hys_feedback:3",
        "doc:hys_attachment:att-ngo",
        "doc:hys_attachment:att-citizen",
        "doc:hys_attachment:att-broken",
    ]
    assert documents["doc:hys_feedback:1"].url == hys.feedback_url(14488, 0)
    assert documents["doc:hys_feedback:1"].retrieved_at == T0
    assert documents["doc:hys_attachment:att-ngo"].title == "Equinet submission.pdf"
    assert documents["doc:hys_attachment:att-broken"].extraction_status == "failed"
    texts = {
        item.document_id: item.text for item in records(result, "asks", "texts.jsonl", DocumentText)
    }
    assert "doc:hys_attachment:att-broken" not in texts
    assert texts["doc:hys_feedback:3"] == ""
    passages = records(result, "asks", "passages.jsonl", Passage)
    assert [(item.passage_id, item.actor_id) for item in passages] == [
        ("passage:doc-hys_feedback-1:1", "actor:tr:718971811339-46"),
        ("passage:doc-hys_feedback-2:1", CITIZENS_ACTOR_ID),
        ("passage:doc-hys_attachment-att-ngo:1", "actor:tr:718971811339-46"),
        ("passage:doc-hys_attachment-att-citizen:1", CITIZENS_ACTOR_ID),
    ]
    assert all(span_matches(item.span, texts[item.document_id]) for item in passages)
    assert passages[0].language == "en"
    assert passages[0].submitted_at == datetime(2021, 8, 6, 23, 57, 37, tzinfo=hys.HYS_TIMEZONE)

    actors = {item.actor_id: item for item in records(result, "actors", "actors.jsonl", Actor)}
    assert list(actors) == [
        CITIZENS_ACTOR_ID,
        "actor:mep:125042",
        "actor:mep:197721",
        "actor:name:hys_feedback.acme-robotics",
        "actor:tr:718971811339-46",
    ]
    assert actors["actor:tr:718971811339-46"].resolution == "register_id"
    assert actors["actor:name:hys_feedback.acme-robotics"].resolution == "unresolved"
    assert actors["actor:mep:197721"].name == "César LUENA"
    authors = {author for item in tabled for author in item.author_ids}
    assert authors <= set(actors)
    assert {item.actor_id for item in passages} <= set(actors)


def test_a_private_person_is_counted_and_never_named(tmp_path: Path) -> None:
    root = build_world(tmp_path)
    result = run(root, make_fetcher(root))

    documents = {
        item.document_id: item
        for item in records(result, "asks", "documents.jsonl", SourceDocument)
    }
    # The file name of a citizen's attachment is their own name, so it is not kept.
    assert documents["doc:hys_attachment:att-citizen"].title is None
    assert documents["doc:hys_feedback:2"].title is None
    actors = records(result, "actors", "actors.jsonl", Actor)
    citizens = [actor for actor in actors if actor.kind == "citizens"]
    assert [(actor.actor_id, actor.name) for actor in citizens] == [
        (CITIZENS_ACTOR_ID, CITIZENS_NAME)
    ]
    metadata = [
        path
        for path in result.bundle.rglob("*.json*")
        if path.name not in ("texts.jsonl", "passages.jsonl")
    ]
    assert len(metadata) > 10
    assert all("Jane" not in path.read_text(encoding="utf-8") for path in metadata)
    assert all("Jeannette" not in path.read_text(encoding="utf-8") for path in metadata)


def test_a_second_run_reuses_every_stage_and_fetches_nothing_new(tmp_path: Path) -> None:
    root = build_world(tmp_path)
    fetcher = make_fetcher(root)
    first = run(root, fetcher)
    before = len(calls(fetcher))
    messages: list[str] = []
    second = run(root, fetcher, messages=messages)

    assert [stage.status for stage in second.manifest.stages] == ["reused"] * 5
    assert second.law == first.law
    assert second.manifest.hardware is None
    assert calls(fetcher)[before:] == []
    assert messages == [
        f"resolved: {AI_ACT} Artificial Intelligence Act",
        "law_texts: reused",
        "amendments: reused",
        "asks: reused",
        "actors: reused",
        "metadata: reused",
    ]
    runs = sorted(path.name for path in (first.bundle / "runs").iterdir())
    assert runs == ["2021-0106-COD-20261003T150000Z.json"]
    assert catalog_path(root).exists()


def test_an_attachment_limit_reads_the_first_ones_and_says_what_it_left(tmp_path: Path) -> None:
    root = build_world(tmp_path)
    fetcher = make_fetcher(root)
    messages: list[str] = []
    limited = run(root, fetcher, attachment_limit=1, messages=messages)

    assert layers(limited)["asks"].status == "partial"
    assert layers(limited)["asks"].reason == (
        "Publication 25429: feedback is not served by the API; "
        "1 of 3 feedback items carry no text; "
        "Attachment limit: 1 of 3 attachments read"
    )
    assert limited.manifest.config == {"attachment_limit": "1"}
    assert stages(limited)["asks"].counts["attachments_read"] == 1
    assert "asks: attachment 1 of 1" in messages
    assert not any("att-citizen" in url for url in calls(fetcher))

    # Lifting the limit is a different input: the stage runs again and reads the rest.
    full = run(root, fetcher)
    assert stages(full)["asks"].status == "complete"
    assert stages(full)["asks"].counts["attachments_read"] == 3
    assert stages(full)["amendments"].status == "reused"
    assert sum("att-ngo" in url for url in calls(fetcher)) == 1


def test_a_clean_consultation_is_complete(tmp_path: Path) -> None:
    only = AI_INITIATIVE.model_copy(update={"publications": AI_INITIATIVE.publications[1:]})
    root = build_world(tmp_path, index=(only,))
    script = {**SCRIPT, "publicationId=14488": page(feedback(1))}
    result = run(root, make_fetcher(root, script))

    asks = layers(result)["asks"]
    assert (asks.status, asks.count, asks.reason) == ("complete", 1, None)
    assert layers(result)["actors"].status == "complete"


# --- Gaps that do not stop the run --------------------------------------------------------

OPEN_FEEDBACK = page(
    feedback(7, organization="Orbital Guild", trNumber=None, referenceInitiative="x")
)
OPEN_SCRIPT: Mapping[str, Answer] = {
    "text=Space Safety Rules": as_json(
        {"initiativeResultDtoPage": {"content": [{"id": 777.0}], "totalElements": 1, "last": True}}
    ),
    "groupInitiatives/777": as_json(
        {
            "shortTitle": "Space safety",
            "publications": [{"id": 900, "reference": "COM(2025) 100 final"}],
        }
    ),
    "publicationId=900": OPEN_FEEDBACK,
}


def open_world(root: Path) -> Path:
    """An open procedure with half its sources absent: every absence must be labelled."""
    return build_world(
        root,
        committee=(amendment(OPEN, "PE1-1"),),
        plenary=None,
        members=None,
        register=None,
        index=None,
    )


def test_an_open_law_with_missing_sources_completes_with_each_gap_labelled(tmp_path: Path) -> None:
    root = open_world(tmp_path)
    result = run(root, make_fetcher(root, OPEN_SCRIPT), "2025/59(cod)")

    law = result.law
    assert (law.procedure_id, law.status, law.completed_on) == (OPEN, "ongoing", None)
    # CELLAR did not answer: nothing it would have said is guessed.
    assert (law.celex_proposal, law.celex_final) == (None, None)
    # Parltrack names exactly one COM document, which joins the consultation.
    assert law.com_reference == "COM(2025)100"
    coverage = layers(result)
    assert {name: (row.status, row.count) for name, row in coverage.items()} == {
        "metadata": ("partial", None),
        "proposal": ("missing", None),
        "parliament_position": ("not_collected", None),
        "final_act": ("not_applicable", None),
        "committee_amendments": ("partial", 1),
        "plenary_amendments": ("not_collected", None),
        "asks": ("partial", 1),
        "actors": ("partial", 1),
        "meetings": ("not_collected", None),
        "votes": ("not_collected", None),
    }
    assert (coverage["metadata"].reason or "").startswith("CELLAR identifiers not resolved: ")
    assert coverage["final_act"].reason == "The procedure is ongoing: there is no final act"
    assert coverage["committee_amendments"].reason == OPEN_PROCEDURE
    assert "unreadable Parltrack dump" in (coverage["plenary_amendments"].reason or "")
    assert "Cannot read the Transparency Register export" in (coverage["asks"].reason or "")
    actors = coverage["actors"].reason or ""
    assert "unreadable Parltrack dump" in actors
    assert "2 of 2 amendment authors have no Member record" in actors
    assert REGISTER_UNAVAILABLE in actors
    by_stage = stages(result)
    assert by_stage["asks"].counts["initiatives_from_index"] == 0
    assert by_stage["asks"].counts["register_entries"] == 0
    assert {name: receipt.status for name, receipt in by_stage.items()} == {
        "metadata": "complete",
        "law_texts": "complete",
        "amendments": "partial",
        "asks": "partial",
        "actors": "partial",
    }
    assert len(by_stage["amendments"].errors) == 1
    named = records(result, "actors", "actors.jsonl", Actor)
    assert [actor.actor_id for actor in named] == ["actor:name:hys_feedback.orbital-guild"]
    assert result.manifest.status == "complete"


def test_a_stage_that_met_a_failure_runs_again_and_recovers(tmp_path: Path) -> None:
    root = open_world(tmp_path)
    fetcher = make_fetcher(root, OPEN_SCRIPT)
    run(root, fetcher, OPEN)
    write_dump(dump_path(root, "ep_meps"), MEMBERS)
    register_path(root).parent.mkdir(parents=True)
    register_path(root).write_text(REGISTER, encoding="utf-8")
    again = run(root, fetcher, OPEN)

    statuses = {name: receipt.status for name, receipt in stages(again).items()}
    # The plenary dump is still absent, so that stage is tried again and stays partial.
    assert statuses == {
        "metadata": "complete",
        "law_texts": "reused",
        "amendments": "partial",
        "asks": "complete",
        "actors": "complete",
    }
    assert layers(again)["actors"].status == "complete"
    assert layers(again)["actors"].count == 3
    assert stages(again)["asks"].counts["register_entries"] == 1


@pytest.mark.parametrize(
    ("answers", "proposal", "final", "transient"),
    [
        (
            {"resource/celex/52021PC0206": FetchError("u", "HTTP 404", 404)},
            ("missing", "CELLAR has no text for 52021PC0206"),
            ("complete", None),
            False,
        ),
        (
            {"resource/celex/32024R1689": FetchError("u", "HTTP 503", 503)},
            ("complete", None),
            ("not_collected", "32024R1689: HTTP 503"),
            True,
        ),
        (
            {"resource/celex/32024R1689": RawResponse(200, "text/html", b"\xff\xfe")},
            ("complete", None),
            ("not_collected", "32024R1689: The text of 32024R1689 is not UTF-8"),
            True,
        ),
        (
            {"resource/celex/32024R1689": xhtml("<p>Words with no structure.</p>")},
            ("complete", None),
            ("partial", cellar.NO_STRUCTURE),
            False,
        ),
    ],
)
def test_a_law_text_that_cannot_be_had_is_a_labelled_gap(
    tmp_path: Path,
    answers: Mapping[str, Answer],
    proposal: tuple[str, str | None],
    final: tuple[str, str | None],
    transient: bool,
) -> None:
    root = build_world(tmp_path)
    result = run(root, make_fetcher(root, {**answers, **SCRIPT, **answers}))

    coverage = layers(result)
    assert (coverage["proposal"].status, coverage["proposal"].reason) == proposal
    assert (coverage["final_act"].status, coverage["final_act"].reason) == final
    receipt = stages(result)["law_texts"]
    assert (receipt.status, bool(receipt.errors)) == (
        ("partial", True) if transient else ("complete", False)
    )
    assert result.manifest.status == "complete"


def test_several_final_acts_are_reported_and_none_is_chosen(tmp_path: Path) -> None:
    root = build_world(tmp_path)
    several = sparql(
        {"final": "32024R1689", "prop": "52021PC0206"},
        {"final": "32024L0001", "prop": "52021PC0206"},
    )
    result = run(root, make_fetcher(root, {**SCRIPT, "dossier_produces_resource_legal": several}))

    # Parltrack names one act, yet CELLAR says there are two: picking either would drop one.
    assert result.law.celex_final is None
    coverage = layers(result)
    assert coverage["metadata"].status == "partial"
    assert coverage["metadata"].reason == (
        "CELLAR lists several acts for one procedure: 52021PC0206, 32024L0001, 32024R1689"
    )
    assert coverage["final_act"].status == "missing"
    assert coverage["final_act"].reason == (
        "Neither CELLAR nor Parltrack names one CELEX number for this text"
    )


def test_parltrack_names_the_final_act_when_cellar_lists_none(tmp_path: Path) -> None:
    root = build_world(tmp_path)
    proposal_only = sparql({"prop": "52021PC0206"})
    script = {**SCRIPT, "dossier_produces_resource_legal": proposal_only}
    result = run(root, make_fetcher(root, script))

    assert result.law.celex_final == "32024R1689"
    assert layers(result)["metadata"].status == "complete"


def test_consultation_failures_are_labelled_and_the_amendments_still_stand(tmp_path: Path) -> None:
    root = build_world(tmp_path, index=(AI_INITIATIVE,))
    script = {
        **SCRIPT,
        "publicationId=14488": RawResponse(200, "text/html", b"<html>maintenance</html>"),
    }
    result = run(root, make_fetcher(root, script))

    asks = layers(result)["asks"]
    assert (asks.status, asks.count) == ("not_collected", 0)
    assert "Publication 25429: feedback is not served by the API" in (asks.reason or "")
    assert "Publication 14488: " in (asks.reason or "")
    receipt = stages(result)["asks"]
    assert receipt.status == "partial"
    assert receipt.counts["publications_unavailable"] == 1
    # Nobody submitted anything readable, so the register was not read and is not blamed.
    assert receipt.counts["register_entries"] == 0
    assert layers(result)["actors"].status == "complete"
    assert layers(result)["actors"].count == 2


def test_an_attachment_that_does_not_download_is_counted_and_retried(tmp_path: Path) -> None:
    root = build_world(tmp_path)
    script = {**SCRIPT, "download/att-ngo": FetchError("u", "HTTP 500", 500)}
    result = run(root, make_fetcher(root, script))

    receipt = stages(result)["asks"]
    assert receipt.status == "partial"
    assert receipt.counts["attachments_failed_download"] == 1
    assert receipt.counts["attachments_read"] == 2
    assert "Attachment att-ngo not downloaded" in receipt.errors[0]
    assert "Attachment att-ngo not downloaded" in (layers(result)["asks"].reason or "")


@pytest.mark.parametrize(
    ("script", "status", "reason"),
    [
        (
            {"text=Artificial Intelligence": as_json({"initiativeResultDtoPage": {"content": []}})},
            "missing",
            "No Have Your Say initiative was found for COM(2021)206",
        ),
        (
            {},
            "not_collected",
            "No Have Your Say initiative was found for COM(2021)206; "
            "Have Your Say title search failed: ",
        ),
    ],
)
def test_a_law_without_a_findable_consultation_keeps_its_amendments(
    tmp_path: Path, script: Mapping[str, Answer], status: str, reason: str
) -> None:
    root = build_world(tmp_path, index=(OTHER_INITIATIVE,))
    result = run(root, make_fetcher(root, {**SCRIPT, **script}))

    asks = layers(result)["asks"]
    assert (asks.status, asks.count) == (status, 0)
    assert (asks.reason or "").startswith(reason)
    assert stages(result)["asks"].counts["publications"] == 0
    assert layers(result)["committee_amendments"].count == 1


def test_a_consultation_with_no_feedback_is_missing_with_a_reason(tmp_path: Path) -> None:
    only = AI_INITIATIVE.model_copy(update={"publications": AI_INITIATIVE.publications[1:]})
    root = build_world(tmp_path, index=(only,))
    result = run(root, make_fetcher(root, {**SCRIPT, "publicationId=14488": page()}))

    asks = layers(result)["asks"]
    assert (asks.status, asks.count, asks.reason) == (
        "missing",
        0,
        "The consultation holds no feedback",
    )


def test_a_law_with_no_com_reference_and_no_authors_still_completes(tmp_path: Path) -> None:
    root = build_world(tmp_path, committee=(amendment(BARE, "PE9-1", ()),), plenary=())
    result = run(root, make_fetcher(root, {}), BARE)

    coverage = layers(result)
    assert (coverage["asks"].status, coverage["asks"].reason) == ("not_collected", NO_COM_REFERENCE)
    assert coverage["plenary_amendments"].status == "missing"
    assert coverage["plenary_amendments"].count == 0
    assert coverage["plenary_amendments"].reason == (
        "The Parltrack dump ep_plenary_amendments holds no amendment for this procedure"
    )
    assert (coverage["actors"].status, coverage["actors"].count) == ("missing", 0)
    assert coverage["actors"].reason == "No amendment author and no submitter is named"
    # A completed procedure with no CELEX anywhere is missing its act, not "not applicable".
    assert coverage["final_act"].status == "missing"


def test_text_holding_unicode_line_separators_survives_the_round_trip(tmp_path: Path) -> None:
    # Real submissions hold U+2028, U+2029 and U+0085; JSON does not escape them, and a
    # reader that splits on them cuts the record in two (seen on the AI Act feedback).
    text = "First\u2028line. Second\u2029paragraph. Third\u0085part."
    only = AI_INITIATIVE.model_copy(update={"publications": AI_INITIATIVE.publications[1:]})
    root = build_world(tmp_path, index=(only,))
    script = {**SCRIPT, "publicationId=14488": page(feedback(1, feedback=text))}
    result = run(root, make_fetcher(root, script))

    texts = records(result, "asks", "texts.jsonl", DocumentText)
    assert [item.text for item in texts] == [text]
    passages = records(result, "asks", "passages.jsonl", Passage)
    assert passages
    assert all(span_matches(item.span, text) for item in passages)
    with pytest.raises(CollectError, match=r"Stage asks has no output named nothing.jsonl"):
        records(result, "asks", "nothing.jsonl", DocumentText)


# --- What stops the run -------------------------------------------------------------------


def test_a_law_with_neither_amendments_nor_asks_stops_with_the_reasons(tmp_path: Path) -> None:
    root = build_world(tmp_path)
    with pytest.raises(CollectError) as caught:
        run(root, make_fetcher(root, {}), BARE)

    message = str(caught.value)
    assert message.startswith(
        f"{BARE} has no amendments and no asks, so there is nothing to link: "
    )
    assert "committee_amendments: The Parltrack dump ep_amendments holds no amendment" in message
    assert f"asks: {NO_COM_REFERENCE}" in message
    assert not (bundle_path(root, BARE) / "manifest.json").exists()


def test_an_empty_query_and_a_missing_catalog_source_are_explicit_errors(tmp_path: Path) -> None:
    root = build_world(tmp_path, dossiers=None)
    with pytest.raises(CollectError, match="The law query is empty"):
        run(root, make_fetcher(root), "   ")
    with pytest.raises(CollectError, match="The procedure catalog cannot be built or read"):
        run(root, make_fetcher(root))
    assert not catalog_path(root).exists()


def test_a_stage_file_that_no_longer_validates_stops_the_run(tmp_path: Path) -> None:
    root = build_world(tmp_path)
    fetcher = make_fetcher(root)
    first = run(root, fetcher)
    output = next(
        item for item in stages(first)["actors"].outputs if item.path.endswith("actors.jsonl")
    )
    path = first.bundle / output.path
    broken = b'{"actor_id": "not an actor"}\n'
    path.write_bytes(broken)
    receipt_path = path.with_name(RECEIPT_NAME)
    receipt = receipt_path.read_text(encoding="utf-8")
    forged = receipt.replace(output.sha256, hashlib.sha256(broken).hexdigest())
    receipt_path.write_text(forged, encoding="utf-8")
    published = first.manifest_path.read_bytes()

    with pytest.raises(CollectError, match=r"actors.jsonl of stage actors failed validation"):
        run(root, fetcher)
    assert first.manifest_path.read_bytes() == published


# --- Resolving the query ------------------------------------------------------------------


def catalog_and_fetcher(tmp_path: Path, script: Mapping[str, Answer]) -> tuple[Path, CachedFetcher]:
    root = build_world(tmp_path)
    return root, make_fetcher(root, script)


@pytest.mark.parametrize(
    "query",
    [
        "2021/0106(COD)",
        "2021/106 cod",
        "32024R1689",
        "CELEX:52021PC0206",
        "COM(2021) 206 final",
        "dsa",
    ],
)
def test_identifiers_resolve_from_the_catalog_without_asking_cellar(
    tmp_path: Path, query: str
) -> None:
    root, fetcher = catalog_and_fetcher(tmp_path, {})
    catalog = load_catalog(root)
    if query == "dsa":
        # An alias whose procedure the catalog lacks is ignored, never trusted blindly.
        with pytest.raises(CollectError, match="'dsa' matches no title"):
            resolve_procedure(parse_query(query), catalog, fetcher)
    else:
        assert resolve_procedure(parse_query(query), catalog, fetcher).procedure_id == AI_ACT
    assert calls(fetcher) == []
    assert {ALIASES[name] for name in ("ai act", "aia")} == {AI_ACT}


def test_a_title_resolves_and_a_close_race_lists_the_choices(tmp_path: Path) -> None:
    root, fetcher = catalog_and_fetcher(tmp_path, {})
    catalog = load_catalog(root)

    found = resolve_procedure(parse_query("space safety rules"), catalog, fetcher)
    assert found.procedure_id == OPEN
    with pytest.raises(CollectError) as caught:
        resolve_procedure(parse_query("Widget Safety"), catalog, fetcher)
    assert (
        str(caught.value) == "'Widget Safety' matches several procedures in the procedure catalog"
    )
    assert caught.value.choices == (
        "2030/0001(COD)  Widget Safety",
        "2030/0002(COD)  Widget Safety",
    )
    with pytest.raises(CollectError) as none:
        resolve_procedure(parse_query("fisheries quotas"), catalog, fetcher)
    assert none.value.choices == ()


def test_a_reference_shared_or_unknown_is_not_guessed(tmp_path: Path) -> None:
    root, fetcher = catalog_and_fetcher(tmp_path, {})
    catalog = load_catalog(root)

    with pytest.raises(CollectError) as shared:
        resolve_procedure(parse_query("COM(2030)5"), catalog, fetcher)
    assert str(shared.value) == "COM(2030)5 names several procedures (Parltrack dossiers)"
    assert len(shared.value.choices) == 2
    with pytest.raises(CollectError) as unknown:
        resolve_procedure(parse_query("2031/0001(COD)"), catalog, fetcher)
    assert str(unknown.value) == (
        "2031/0001(COD) is not a procedure in the catalog (Parltrack dossiers)"
    )
    with pytest.raises(CollectError, match="CELLAR could not resolve 32099R0001"):
        resolve_procedure(parse_query("32099R0001"), catalog, fetcher)


def test_cellar_resolves_a_number_the_catalog_does_not_hold(tmp_path: Path) -> None:
    reference = sparql({"ref": "2025/0059/COD"})
    root, fetcher = catalog_and_fetcher(tmp_path, {"reference_procedure": reference})
    catalog = load_catalog(root)

    assert resolve_procedure(parse_query("32099R0001"), catalog, fetcher).procedure_id == OPEN
    assert resolve_procedure(parse_query("COM(2099) 7"), catalog, fetcher).procedure_id == OPEN
    assert '"52099PC0007"' in calls(fetcher)[-1]
