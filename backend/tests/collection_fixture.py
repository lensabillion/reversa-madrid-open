"""Deterministic shared collection records with exact source spans and unknowns."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from influence.schemas.atlas import (
    CITIZENS_ACTOR_ID,
    Actor,
    ActorAlias,
    Amendment,
    ArticleVersion,
    AtlasRecord,
    DocumentText,
    LawRecord,
    LayerCoverage,
    OutputFile,
    Passage,
    RunManifest,
    SourceDocument,
    SourceSpan,
    SpanField,
    StageReceipt,
    document_id,
    mep_actor_id,
    named_actor_id,
    register_actor_id,
)

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "atlas"

LAW_A = "2099/0001(COD)"
LAW_B = "2099/0002(COD)"
RETRIEVED = datetime(2026, 10, 3, 10, 0, tzinfo=UTC)


MAKERS = register_actor_id("123456789012-34")
WATCH = register_actor_id("234567890123-45")
CITY = register_actor_id("345678901234-56")
ACME_BELGIUM = register_actor_id("456789012345-67")
ACME_HOLDINGS = register_actor_id("567890123456-78")
ACME = named_actor_id("hys_feedback", "acme")
MEP_ONE = mep_actor_id(900001)
MEP_TWO = mep_actor_id(900002)

DOC_MAKERS = document_id("hys_feedback", "9000001")
DOC_WATCH = document_id("hys_feedback", "9000002")
DOC_CITY = document_id("hys_attachment", "fixture0003")
DOC_ACME = document_id("hys_feedback", "9000004")
DOC_UNDATED = document_id("hys_attachment", "fixture0005")
DOC_LABELS = document_id("hys_feedback", "9000006")
DOC_AMENDMENTS_A = document_id("parltrack", "fixture-a-amendments")
DOC_AMENDMENTS_B = document_id("parltrack", "fixture-b-amendments")
DOC_PROPOSAL_A = document_id("cellar", "52099PC0001")
DOC_POSITION_A = document_id("ep_api", "TA-99-2099-0001")
DOC_FINAL_A = document_id("cellar", "32099R0001")
DOC_PROPOSAL_B = document_id("cellar", "52099PC0002")

TEXTS = {
    DOC_MAKERS: (
        "Widget Makers Europe welcomes the proposal. In Article 5(1), providers shall keep "
        "technical logs for at least six months after placing the widget on the market. "
        "A shorter period would leave incidents untraceable."
    ),
    DOC_WATCH: (
        "Consumer Watch disagrees with the logging duty. Providers should not be required "
        "to keep technical logs for any fixed period, because logs expose user data."
    ),
    DOC_CITY: (
        "Position of the City Network.\n\nIn Article 9(2), replace 'shall' with "
        "'may': the authority may publish the assessment where publication serves "
        "the public interest."
    ),
    DOC_ACME: (
        "Acme supports a transition period. Small providers need at least twelve months "
        "before Article 5 applies."
    ),
    DOC_UNDATED: (
        "Providers shall keep technical logs for at least six months after placing the "
        "widget on the market."
    ),
    DOC_LABELS: (
        "Label Alliance asks that Article 3 require the energy grade to be printed in a "
        "font no smaller than the product name."
    ),
    DOC_PROPOSAL_A: (
        "Article 5\n1. Providers shall keep technical logs.\n\n"
        "Article 9\n2. The authority shall publish the assessment."
    ),
    DOC_POSITION_A: (
        "Article 5\n1. Providers shall keep technical logs for at least six months after "
        "placing the widget on the market.\n\n"
        "Article 9\n2. The authority may publish the assessment."
    ),
    DOC_FINAL_A: (
        "Article 6\n1. Providers shall keep technical logs for at least six months after "
        "placing the widget on the market.\n\n"
        "Article 11\n2. The authority may publish a summary of the assessment."
    ),
    DOC_PROPOSAL_B: "Article 3\nThe label shall state the energy grade.",
}

AM1_OLD = "Providers shall keep technical logs."
AM1_NEW = (
    "Providers shall keep technical logs for at least six months after placing the widget "
    "on the market."
)
AM2_OLD = "The authority shall publish the assessment."
AM2_NEW = "The authority may publish the assessment."
AM3_OLD = "The label shall state the energy grade."
AM3_NEW = (
    "The label shall state the energy grade, printed in a font no smaller than the product name."
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _span(record_id: str, source: str, quote: str, field: SpanField = "text") -> SourceSpan:
    """Locate `quote` in `source`, so no offset in the fixture is typed by hand."""
    start = source.index(quote)
    return SourceSpan(
        record_id=record_id, field=field, start=start, end=start + len(quote), text=quote
    )


def _doc_span(doc: str, quote: str) -> SourceSpan:
    return _span(doc, TEXTS[doc], quote)


@dataclass(frozen=True)
class CollectionFixture:
    laws: tuple[LawRecord, ...]
    documents: tuple[SourceDocument, ...]
    document_texts: tuple[DocumentText, ...]
    actors: tuple[Actor, ...]
    passages: tuple[Passage, ...]
    amendments: tuple[Amendment, ...]
    articles: tuple[ArticleVersion, ...]
    manifests: tuple[RunManifest, ...]

    def tables(self) -> dict[str, tuple[AtlasRecord, ...]]:
        """File stem -> records, in the order the files are written."""
        return {
            "laws": self.laws,
            "documents": self.documents,
            "document_texts": self.document_texts,
            "actors": self.actors,
            "passages": self.passages,
            "amendments": self.amendments,
            "articles": self.articles,
            "manifests": self.manifests,
        }


def _coverage_a() -> tuple[LayerCoverage, ...]:
    return (
        LayerCoverage(layer="metadata", status="complete", count=1),
        LayerCoverage(layer="proposal", status="complete", count=2),
        LayerCoverage(layer="parliament_position", status="complete", count=2),
        LayerCoverage(layer="final_act", status="complete", count=2),
        LayerCoverage(layer="committee_amendments", status="complete", count=2),
        LayerCoverage(
            layer="plenary_amendments", status="missing", count=0, reason="None were tabled"
        ),
        LayerCoverage(
            layer="asks",
            status="partial",
            count=5,
            reason="1 of 5 submissions has no publication date",
        ),
        LayerCoverage(
            layer="actors", status="partial", count=7, reason="1 name matches two register entries"
        ),
        LayerCoverage(layer="meetings", status="not_collected", reason="Connector not built"),
        LayerCoverage(layer="votes", status="not_collected", reason="Connector not built"),
    )


def _coverage_b() -> tuple[LayerCoverage, ...]:
    return (
        LayerCoverage(layer="metadata", status="complete", count=1),
        LayerCoverage(layer="proposal", status="complete", count=1),
        LayerCoverage(layer="parliament_position", status="missing", reason="No plenary vote yet"),
        LayerCoverage(layer="final_act", status="missing", reason="Negotiation in progress"),
        LayerCoverage(
            layer="committee_amendments",
            status="stale",
            count=1,
            reason="The amendment dump ends before the procedure does",
            source_updated_on=date(2099, 2, 3),
        ),
        LayerCoverage(layer="asks", status="complete", count=1),
        LayerCoverage(layer="actors", status="complete", count=2),
    )


def _laws() -> tuple[LawRecord, ...]:
    return (
        LawRecord(
            procedure_id=LAW_A,
            title="Fixture Regulation on widget safety",
            status="completed",
            stage_reached="Procedure completed",
            celex_proposal="52099PC0001",
            celex_final="32099R0001",
            com_reference="COM(2099)1",
            subjects=("3.40.06 Electronics", "4.60.08 Safety of products"),
            lead_committee="IMCO",
            proposed_on=date(2099, 1, 10),
            completed_on=date(2099, 11, 30),
            coverage=_coverage_a(),
        ),
        LawRecord(
            procedure_id=LAW_B,
            title="Fixture Directive on gadget labelling",
            status="ongoing",
            stage_reached="Awaiting committee decision",
            celex_proposal="52099PC0002",
            com_reference="COM(2099)2",
            subjects=("4.60.02 Consumer information",),
            lead_committee="IMCO",
            proposed_on=date(2099, 6, 1),
            coverage=_coverage_b(),
        ),
    )


def _document(
    doc: str,
    procedure: str | None,
    kind: str,
    url: str,
    published: datetime | None,
    *,
    title: str | None = None,
) -> SourceDocument:
    text = TEXTS.get(doc)
    return SourceDocument.model_validate(
        {
            "document_id": doc,
            "procedure_id": procedure,
            "source_kind": kind,
            "url": url,
            "title": title,
            "published_at": published,
            "retrieved_at": RETRIEVED,
            "sha256": _sha256(text if text is not None else doc),
            "media_type": "text/plain" if text is not None else "application/json",
            "language": "en",
            "extraction_status": "extracted" if text is not None else "not_applicable",
            "extraction_method": "fixture" if text is not None else None,
            "text_characters": len(text) if text is not None else None,
            "reuse_terms": "Invented for tests",
        }
    )


def _when(month: int, day: int) -> datetime:
    return datetime(2099, month, day, 12, 0, tzinfo=UTC)


def _documents() -> tuple[SourceDocument, ...]:
    base = "https://example.invalid/fixture"
    return (
        _document(DOC_MAKERS, LAW_A, "hys_feedback", f"{base}/feedback/9000001", _when(2, 1)),
        _document(DOC_WATCH, LAW_A, "hys_feedback", f"{base}/feedback/9000002", _when(2, 3)),
        _document(DOC_CITY, LAW_A, "hys_attachment", f"{base}/download/0003", _when(2, 5)),
        _document(DOC_ACME, LAW_A, "hys_feedback", f"{base}/feedback/9000004", _when(2, 7)),
        _document(DOC_UNDATED, LAW_A, "hys_attachment", f"{base}/download/0005", None),
        _document(DOC_LABELS, LAW_B, "hys_feedback", f"{base}/feedback/9000006", _when(7, 1)),
        _document(DOC_AMENDMENTS_A, LAW_A, "parltrack", f"{base}/amendments-a", _when(4, 1)),
        _document(DOC_AMENDMENTS_B, LAW_B, "parltrack", f"{base}/amendments-b", _when(9, 1)),
        _document(DOC_PROPOSAL_A, LAW_A, "cellar", f"{base}/celex/52099PC0001", _when(1, 10)),
        _document(DOC_POSITION_A, LAW_A, "ep_api", f"{base}/TA-99-2099-0001", _when(6, 14)),
        _document(DOC_FINAL_A, LAW_A, "cellar", f"{base}/celex/32099R0001", _when(11, 30)),
        _document(DOC_PROPOSAL_B, LAW_B, "cellar", f"{base}/celex/52099PC0002", _when(6, 1)),
    )


def _organisation(actor_id: str, name: str, category: str, cost: float | None) -> Actor:
    return Actor(
        actor_id=actor_id,
        kind="organisation",
        name=name,
        register_id=actor_id.removeprefix("actor:tr:"),
        category=category,
        country="BEL",
        declared_cost_eur=cost,
        declared_cost_raw=None if cost is None else f"{cost:.0f}",
        aliases=(ActorAlias(name=name, source_kind="register"),),
        resolution="register_id",
        resolution_score=1.0,
    )


def _actors() -> tuple[Actor, ...]:
    return (
        _organisation(MAKERS, "Widget Makers Europe", "Trade and business associations", 450000),
        _organisation(WATCH, "Consumer Watch", "Non-governmental organisations", 80000),
        _organisation(CITY, "City Network", "Organisations of local authorities", None),
        _organisation(ACME_BELGIUM, "Acme Belgium", "Companies & groups", 25000),
        _organisation(ACME_HOLDINGS, "Acme Holdings", "Companies & groups", 900000),
        Actor(
            actor_id=ACME,
            kind="organisation",
            name="Acme",
            country="BEL",
            aliases=(ActorAlias(name="Acme", source_kind="hys_feedback", document_id=DOC_ACME),),
            resolution="ambiguous",
            resolution_score=1.0,
            candidate_ids=(ACME_BELGIUM, ACME_HOLDINGS),
        ),
        Actor(
            actor_id=named_actor_id("hys_attachment", "label alliance"),
            kind="organisation",
            name="Label Alliance",
            resolution="unresolved",
        ),
        Actor(
            actor_id=MEP_ONE,
            kind="mep",
            name="Alex Example",
            mep_id=900001,
            country="ESP",
            political_group="Group One",
            resolution="mep_id",
        ),
        Actor(
            actor_id=MEP_TWO,
            kind="mep",
            name="Robin Sample",
            mep_id=900002,
            country="DEU",
            political_group="Group Two",
            resolution="mep_id",
        ),
        Actor(
            actor_id=CITIZENS_ACTOR_ID,
            kind="citizens",
            name="Private individuals (counted, not named)",
            resolution="unresolved",
        ),
    )


LABEL_ALLIANCE = named_actor_id("hys_attachment", "label alliance")


def _passage(
    key: str, law: str, doc: str, actor: str, quote: str, submitted: datetime | None
) -> Passage:
    return Passage(
        passage_id=f"passage:{key}",
        procedure_id=law,
        document_id=doc,
        actor_id=actor,
        span=_doc_span(doc, quote),
        submitted_at=submitted,
        language="en",
    )


def _passages() -> tuple[Passage, ...]:
    return (
        _passage(
            "makers-1",
            LAW_A,
            DOC_MAKERS,
            MAKERS,
            "In Article 5(1), providers shall keep technical logs for at least six months "
            "after placing the widget on the market.",
            _when(2, 1),
        ),
        _passage(
            "watch-1",
            LAW_A,
            DOC_WATCH,
            WATCH,
            "Providers should not be required to keep technical logs for any fixed period, "
            "because logs expose user data.",
            _when(2, 3),
        ),
        _passage(
            "city-1",
            LAW_A,
            DOC_CITY,
            CITY,
            "In Article 9(2), replace 'shall' with 'may': the authority "
            "may publish the assessment where publication serves the public interest.",
            _when(2, 5),
        ),
        _passage(
            "acme-1",
            LAW_A,
            DOC_ACME,
            ACME,
            "Small providers need at least twelve months before Article 5 applies.",
            _when(2, 7),
        ),
        _passage("undated-1", LAW_A, DOC_UNDATED, MAKERS, TEXTS[DOC_UNDATED], None),
        _passage(
            "labels-1",
            LAW_B,
            DOC_LABELS,
            LABEL_ALLIANCE,
            TEXTS[DOC_LABELS],
            _when(7, 1),
        ),
    )


def _amendments() -> tuple[Amendment, ...]:
    return (
        Amendment(
            amendment_id="am:2099-0001-COD:IMCO:101",
            procedure_id=LAW_A,
            document_id=DOC_AMENDMENTS_A,
            stage="committee",
            committee="IMCO",
            number=101,
            author_ids=(MEP_ONE,),
            author_names=("Alex Example",),
            tabled_on=date(2099, 4, 1),
            target_provision="Article 5 - paragraph 1",
            old_text=AM1_OLD,
            new_text=AM1_NEW,
            justification="Logs kept for a defined period make incidents traceable.",
            language="en",
        ),
        Amendment(
            amendment_id="am:2099-0001-COD:IMCO:102",
            procedure_id=LAW_A,
            document_id=DOC_AMENDMENTS_A,
            stage="committee",
            committee="IMCO",
            number=102,
            author_ids=(MEP_ONE, MEP_TWO),
            author_names=("Alex Example", "Robin Sample"),
            tabled_on=date(2099, 4, 1),
            target_provision="Article 9 - paragraph 2",
            old_text=AM2_OLD,
            new_text=AM2_NEW,
            language="en",
        ),
        Amendment(
            amendment_id="am:2099-0002-COD:IMCO:7",
            procedure_id=LAW_B,
            document_id=DOC_AMENDMENTS_B,
            stage="committee",
            committee="IMCO",
            number=7,
            author_ids=(MEP_TWO,),
            author_names=("Robin Sample",),
            tabled_on=date(2099, 9, 1),
            target_provision="Article 3",
            old_text=AM3_OLD,
            new_text=AM3_NEW,
            language="en",
        ),
    )


AM1, AM2, AM3 = (
    "am:2099-0001-COD:IMCO:101",
    "am:2099-0001-COD:IMCO:102",
    "am:2099-0002-COD:IMCO:7",
)

ARTICLE_TEXTS = {
    "art:52099PC0001:article-5-1": "Providers shall keep technical logs.",
    "art:52099PC0001:article-9-2": "The authority shall publish the assessment.",
    "art:TA-99-2099-0001:article-5-1": AM1_NEW,
    "art:TA-99-2099-0001:article-9-2": AM2_NEW,
    "art:32099R0001:article-6-1": AM1_NEW,
    "art:32099R0001:article-11-2": "The authority may publish a summary of the assessment.",
    "art:52099PC0002:article-3": AM3_OLD,
}


def _article(
    article_id: str, law: str, doc: str, stage: str, provision: str, when: date
) -> ArticleVersion:
    return ArticleVersion.model_validate(
        {
            "article_id": article_id,
            "procedure_id": law,
            "document_id": doc,
            "stage": stage,
            "provision": provision,
            "kind": "paragraph" if "(" in provision else "article",
            "text": ARTICLE_TEXTS[article_id],
            "version_date": when,
        }
    )


def _articles() -> tuple[ArticleVersion, ...]:
    proposed, position, final = date(2099, 1, 10), date(2099, 6, 14), date(2099, 11, 30)
    return (
        _article(
            "art:52099PC0001:article-5-1",
            LAW_A,
            DOC_PROPOSAL_A,
            "proposal",
            "Article 5(1)",
            proposed,
        ),
        _article(
            "art:52099PC0001:article-9-2",
            LAW_A,
            DOC_PROPOSAL_A,
            "proposal",
            "Article 9(2)",
            proposed,
        ),
        _article(
            "art:TA-99-2099-0001:article-5-1",
            LAW_A,
            DOC_POSITION_A,
            "parliament_position",
            "Article 5(1)",
            position,
        ),
        _article(
            "art:TA-99-2099-0001:article-9-2",
            LAW_A,
            DOC_POSITION_A,
            "parliament_position",
            "Article 9(2)",
            position,
        ),
        # The final act renumbers: Article 5 became 6 and Article 9 became 11.
        _article(
            "art:32099R0001:article-6-1", LAW_A, DOC_FINAL_A, "final_act", "Article 6(1)", final
        ),
        _article(
            "art:32099R0001:article-11-2",
            LAW_A,
            DOC_FINAL_A,
            "final_act",
            "Article 11(2)",
            final,
        ),
        _article(
            "art:52099PC0002:article-3",
            LAW_B,
            DOC_PROPOSAL_B,
            "proposal",
            "Article 3",
            date(2099, 6, 1),
        ),
    )


def _manifests() -> tuple[RunManifest, ...]:
    return (
        RunManifest(
            run_id="run:fixture-a",
            query="widget safety",
            procedure_id=LAW_A,
            status="complete",
            started_at=RETRIEVED,
            completed_at=datetime(2026, 10, 3, 10, 2, tzinfo=UTC),
            code_revision="fixture",
            config={"data_root": "tests/fixtures/atlas"},
            hardware="fixture",
            stages=(
                StageReceipt(
                    stage="collect",
                    status="complete",
                    input_hash=_sha256(LAW_A),
                    seconds=1.5,
                    counts={"amendments": 2, "documents": 10, "passages": 5},
                    outputs=(OutputFile(path="amendments.jsonl", sha256=_sha256("a"), records=2),),
                ),
                StageReceipt(
                    stage="actors",
                    status="partial",
                    input_hash=_sha256(f"{LAW_A}/actors"),
                    seconds=0.2,
                    counts={"actors": 7, "ambiguous": 1},
                    errors=("1 name matches two register entries",),
                ),
            ),
            coverage=_coverage_a(),
        ),
        RunManifest(
            run_id="run:fixture-b",
            query=LAW_B,
            procedure_id=LAW_B,
            status="running",
            started_at=RETRIEVED,
            code_revision="fixture",
            coverage=_coverage_b(),
        ),
    )


def build_fixture() -> CollectionFixture:
    passages = _passages()
    return CollectionFixture(
        laws=_laws(),
        documents=_documents(),
        document_texts=tuple(
            DocumentText(document_id=doc, text=text) for doc, text in TEXTS.items()
        ),
        actors=_actors(),
        passages=passages,
        amendments=_amendments(),
        articles=_articles(),
        manifests=_manifests(),
    )


def render(records: tuple[AtlasRecord, ...]) -> str:
    """JSON Lines with sorted keys, so a contract change shows as a readable diff."""
    return "".join(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )


def write_fixture(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for stem, records in build_fixture().tables().items():
        (directory / f"{stem}.jsonl").write_text(render(records), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write_fixture(FIXTURE_DIRECTORY)
    print(f"Wrote the Atlas fixture to {FIXTURE_DIRECTORY}")
