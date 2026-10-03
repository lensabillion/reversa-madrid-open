"""An invented two-law Atlas bundle that exercises every shared contract.

Agents building parts 3 to 8 develop against these records while real collection is still
running. The laws, actors and texts are made up (procedure year 2099), so nothing here
can be mistaken for a finding, and a passing test on it is not accuracy evidence.

Seven cases are covered, each named in `CASES`: a supported copy, an opposite request, a
short shall/may edit, an ambiguous actor, a missing date, a missing final act and a
partial outcome.

Run `uv run --directory backend --locked python tests/atlas_fixture.py` to rewrite the
files under `tests/fixtures/atlas/` after changing a contract; `test_atlas_contracts.py`
fails while the committed files differ from what this module builds.
"""

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
    Ask,
    AtlasRecord,
    Candidate,
    DocumentText,
    Forecast,
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    LawRecord,
    LayerCoverage,
    LinkAssessment,
    Outcome,
    OutputFile,
    Passage,
    PublicPosition,
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

# case name -> the link (or actor) record that demonstrates it.
CASES = {
    "supported_copy": "link:a-am1-makers",
    "opposite_request": "link:a-am1-watch",
    "short_shall_may_edit": "link:a-am2-city",
    "ambiguous_actor": "actor:name:hys_feedback.acme",
    "missing_date": "link:a-am1-undated",
    "missing_final_act": "outcome:b-ask-labels-final",
    "partial_outcome": "outcome:a-ask-city-final",
}

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
DOC_STATEMENT = document_id("public_statement", "makers-press-2098-11")
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
    DOC_STATEMENT: (
        "Widget Makers Europe said today that it supports strong traceability rules for "
        "every widget sold in the Union."
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
SIX_MONTHS = (
    "providers shall keep technical logs for at least six months after placing the widget "
    "on the market"
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
class AtlasFixture:
    laws: tuple[LawRecord, ...]
    documents: tuple[SourceDocument, ...]
    document_texts: tuple[DocumentText, ...]
    actors: tuple[Actor, ...]
    passages: tuple[Passage, ...]
    amendments: tuple[Amendment, ...]
    articles: tuple[ArticleVersion, ...]
    asks: tuple[Ask, ...]
    candidates: tuple[Candidate, ...]
    links: tuple[LinkAssessment, ...]
    outcomes: tuple[Outcome, ...]
    positions: tuple[PublicPosition, ...]
    forecasts: tuple[Forecast, ...]
    graphs: tuple[GraphSnapshot, ...]
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
            "asks": self.asks,
            "candidates": self.candidates,
            "links": self.links,
            "outcomes": self.outcomes,
            "positions": self.positions,
            "forecasts": self.forecasts,
            "graphs": self.graphs,
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
        _document(
            DOC_STATEMENT,
            None,
            "public_statement",
            f"{base}/press/2098-11",
            datetime(2098, 11, 20, 9, 0, tzinfo=UTC),
            title="Press release",
        ),
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


def _ask(
    key: str,
    passage: Passage,
    *,
    change: str,
    provision: str | None,
    direction: str,
) -> Ask:
    return Ask.model_validate(
        {
            "ask_id": f"ask:{key}",
            "procedure_id": passage.procedure_id,
            "actor_id": passage.actor_id,
            "document_id": passage.document_id,
            "passage_id": passage.passage_id,
            "span": passage.span,
            "requested_change": change,
            "target_provision": provision,
            "direction": direction,
            "submitted_at": passage.submitted_at,
            "language": "en",
            "extraction_method": "fixture",
        }
    )


def _asks(passages: tuple[Passage, ...]) -> tuple[Ask, ...]:
    makers, watch, city, acme, undated, labels = passages
    return (
        _ask(
            "a-makers",
            makers,
            change="Keep logs for at least six months",
            provision="Article 5(1)",
            direction="stricter",
        ),
        _ask(
            "a-watch",
            watch,
            change="No fixed period for keeping logs",
            provision="Article 5(1)",
            direction="weaker",
        ),
        _ask(
            "a-city",
            city,
            change="Replace shall with may",
            provision="Article 9(2)",
            direction="weaker",
        ),
        _ask(
            "a-acme",
            acme,
            change="Twelve-month transition for small providers",
            provision="Article 5",
            direction="delay",
        ),
        _ask(
            "a-undated",
            undated,
            change="Keep logs for at least six months",
            provision=None,
            direction="stricter",
        ),
        _ask(
            "b-labels",
            labels,
            change="Print the energy grade as large as the product name",
            provision="Article 3",
            direction="stricter",
        ),
    )


def _candidate(key: str, law: str, amendment: str, ask: str, rank: int, score: float) -> Candidate:
    return Candidate(
        candidate_id=f"cand:{key}",
        procedure_id=law,
        amendment_id=amendment,
        ask_id=ask,
        lexical_rank=rank,
        retrieval_score=score,
        method="fixture",
    )


def _candidates() -> tuple[Candidate, ...]:
    return (
        _candidate("a-am1-makers", LAW_A, AM1, "ask:a-makers", 1, 0.0328),
        _candidate("a-am1-undated", LAW_A, AM1, "ask:a-undated", 2, 0.0323),
        _candidate("a-am1-watch", LAW_A, AM1, "ask:a-watch", 3, 0.0317),
        _candidate("a-am1-acme", LAW_A, AM1, "ask:a-acme", 4, 0.0312),
        _candidate("a-am2-city", LAW_A, AM2, "ask:a-city", 1, 0.0328),
        _candidate("b-am3-labels", LAW_B, AM3, "ask:b-labels", 1, 0.0328),
    )


def _links() -> tuple[LinkAssessment, ...]:
    copied_amendment = _span(AM1, AM1_NEW, "for at least six months", "new_text")
    font = "printed in a font no smaller than the product name"
    return (
        LinkAssessment(
            link_id="link:a-am1-makers",
            procedure_id=LAW_A,
            candidate_id="cand:a-am1-makers",
            amendment_id=AM1,
            ask_id="ask:a-makers",
            status="published",
            tier="copied",
            support_score=0.94,
            signals={"shared_rare_phrase": 1.0, "same_direction": 1.0, "polarity_conflict": 0.0},
            amendment_spans=(copied_amendment,),
            ask_spans=(_doc_span(DOC_MAKERS, "for at least six months"),),
            time_eligibility="ask_first",
            method="fixture",
            method_revision="fixture-1",
        ),
        LinkAssessment(
            link_id="link:a-am1-watch",
            procedure_id=LAW_A,
            candidate_id="cand:a-am1-watch",
            amendment_id=AM1,
            ask_id="ask:a-watch",
            status="contradicted",
            support_score=0.08,
            signals={"shared_rare_phrase": 0.4, "same_direction": 0.0, "polarity_conflict": 1.0},
            amendment_spans=(_span(AM1, AM1_NEW, "shall keep technical logs", "new_text"),),
            ask_spans=(_doc_span(DOC_WATCH, "should not be required to keep technical logs"),),
            time_eligibility="ask_first",
            method="fixture",
            method_revision="fixture-1",
            limitations=("The ask opposes the duty the amendment extends.",),
        ),
        LinkAssessment(
            link_id="link:a-am2-city",
            procedure_id=LAW_A,
            candidate_id="cand:a-am2-city",
            amendment_id=AM2,
            ask_id="ask:a-city",
            status="unconfirmed",
            tier="same_direction",
            support_score=0.55,
            signals={"shared_rare_phrase": 0.0, "same_direction": 1.0, "polarity_conflict": 0.0},
            amendment_spans=(_span(AM2, AM2_NEW, "may", "new_text"),),
            ask_spans=(_doc_span(DOC_CITY, "replace 'shall' with 'may'"),),
            time_eligibility="ask_first",
            method="fixture",
            method_revision="fixture-1",
            limitations=("A one-word edit cannot pass the copied tier on rarity alone.",),
        ),
        LinkAssessment(
            link_id="link:a-am1-undated",
            procedure_id=LAW_A,
            candidate_id="cand:a-am1-undated",
            amendment_id=AM1,
            ask_id="ask:a-undated",
            status="unconfirmed",
            tier="copied",
            support_score=0.94,
            signals={"shared_rare_phrase": 1.0, "same_direction": 1.0, "polarity_conflict": 0.0},
            amendment_spans=(copied_amendment,),
            ask_spans=(_doc_span(DOC_UNDATED, "for at least six months"),),
            time_eligibility="unknown_date",
            method="fixture",
            method_revision="fixture-1",
            limitations=("The source has no publication date, so it cannot be an origin.",),
        ),
        LinkAssessment(
            link_id="link:a-am1-acme",
            procedure_id=LAW_A,
            candidate_id="cand:a-am1-acme",
            amendment_id=AM1,
            ask_id="ask:a-acme",
            status="insufficient_evidence",
            support_score=0.12,
            signals={"shared_rare_phrase": 0.0, "same_direction": 0.0, "polarity_conflict": 0.0},
            time_eligibility="ask_first",
            method="fixture",
            method_revision="fixture-1",
        ),
        LinkAssessment(
            link_id="link:b-am3-labels",
            procedure_id=LAW_B,
            candidate_id="cand:b-am3-labels",
            amendment_id=AM3,
            ask_id="ask:b-labels",
            status="published",
            tier="reworded",
            support_score=0.81,
            signals={"shared_rare_phrase": 0.7, "same_direction": 1.0, "polarity_conflict": 0.0},
            amendment_spans=(_span(AM3, AM3_NEW, font, "new_text"),),
            ask_spans=(_doc_span(DOC_LABELS, "font no smaller than the product name"),),
            time_eligibility="ask_first",
            method="fixture",
            method_revision="fixture-1",
        ),
    )


def _article_span(article_id: str, quote: str) -> SourceSpan:
    return _span(article_id, ARTICLE_TEXTS[article_id], quote)


def _outcomes() -> tuple[Outcome, ...]:
    position_logs = "art:TA-99-2099-0001:article-5-1"
    final_logs = "art:32099R0001:article-6-1"
    final_publish = "art:32099R0001:article-11-2"
    return (
        Outcome(
            outcome_id="outcome:a-ask-makers-heard",
            procedure_id=LAW_A,
            ask_id="ask:a-makers",
            link_id="link:a-am1-makers",
            amendment_id=AM1,
            relation="via_amendment",
            stage="heard",
            result="full",
            kind="wording",
            spans=(_span(AM1, AM1_NEW, "for at least six months", "new_text"),),
            method="fixture",
        ),
        Outcome(
            outcome_id="outcome:a-ask-makers-position",
            procedure_id=LAW_A,
            ask_id="ask:a-makers",
            link_id="link:a-am1-makers",
            amendment_id=AM1,
            relation="via_amendment",
            stage="parliament_position",
            result="full",
            kind="wording",
            article_id=position_logs,
            spans=(_article_span(position_logs, "for at least six months"),),
            method="fixture",
        ),
        Outcome(
            outcome_id="outcome:a-ask-makers-final",
            procedure_id=LAW_A,
            ask_id="ask:a-makers",
            link_id="link:a-am1-makers",
            amendment_id=AM1,
            relation="via_amendment",
            stage="final_act",
            result="full",
            kind="wording",
            article_id=final_logs,
            spans=(_article_span(final_logs, "for at least six months"),),
            method="fixture",
        ),
        Outcome(
            outcome_id="outcome:a-ask-watch-final",
            procedure_id=LAW_A,
            ask_id="ask:a-watch",
            relation="direct_to_final",
            stage="final_act",
            result="not_observed",
            article_id=final_logs,
            method="fixture",
        ),
        Outcome(
            outcome_id="outcome:a-ask-city-final",
            procedure_id=LAW_A,
            ask_id="ask:a-city",
            amendment_id=AM2,
            relation="via_amendment",
            stage="final_act",
            result="partial",
            kind="reworded",
            article_id=final_publish,
            spans=(_article_span(final_publish, "may publish"),),
            reason="The final act says may, but only for a summary of the assessment.",
            method="fixture",
        ),
        Outcome(
            outcome_id="outcome:a-ask-acme-final",
            procedure_id=LAW_A,
            ask_id="ask:a-acme",
            relation="direct_to_final",
            stage="final_act",
            result="not_observed",
            method="fixture",
        ),
        Outcome(
            outcome_id="outcome:a-ask-undated-final",
            procedure_id=LAW_A,
            ask_id="ask:a-undated",
            relation="direct_to_final",
            stage="final_act",
            result="full",
            kind="wording",
            article_id=final_logs,
            spans=(_article_span(final_logs, "for at least six months"),),
            method="fixture",
        ),
        Outcome(
            outcome_id="outcome:b-ask-labels-heard",
            procedure_id=LAW_B,
            ask_id="ask:b-labels",
            link_id="link:b-am3-labels",
            amendment_id=AM3,
            relation="via_amendment",
            stage="heard",
            result="full",
            kind="reworded",
            spans=(_span(AM3, AM3_NEW, "font no smaller than the product name", "new_text"),),
            method="fixture",
        ),
        Outcome(
            outcome_id="outcome:b-ask-labels-final",
            procedure_id=LAW_B,
            ask_id="ask:b-labels",
            link_id="link:b-am3-labels",
            amendment_id=AM3,
            relation="via_amendment",
            stage="final_act",
            result="unknown",
            reason="No final act: the procedure is still being negotiated.",
            method="fixture",
        ),
    )


def _positions() -> tuple[PublicPosition, ...]:
    return (
        PublicPosition(
            position_id="position:makers-press-2098-11",
            actor_id=MAKERS,
            document_id=DOC_STATEMENT,
            span=_doc_span(DOC_STATEMENT, "supports strong traceability rules"),
            stated_at=datetime(2098, 11, 20, 9, 0, tzinfo=UTC),
            attribution="self_statement",
            topic="4.60.08 Safety of products",
            procedure_id=LAW_A,
            direction="stricter",
        ),
    )


def _forecasts() -> tuple[Forecast, ...]:
    return (
        Forecast(
            forecast_id="forecast:b-ask-labels",
            procedure_id=LAW_B,
            ask_id="ask:b-labels",
            as_of=_when(9, 15),
            event="The requested wording appears in Parliament's first-reading position",
            horizon="Before the plenary vote; no date is set",
            score_type="scenario",
            scenario="Likely if the committee adopts amendment 7 unchanged",
            reasons=("One committee amendment carries the ask.",),
            missing_features=("rapporteur_draft", "council_position"),
            model_revision="fixture-1",
        ),
    )


def _node(record_id: str, kind: str, label: str) -> GraphNode:
    return GraphNode.model_validate(
        {"node_id": record_id, "kind": kind, "label": label, "record_id": record_id}
    )


def _graphs(links: tuple[LinkAssessment, ...]) -> tuple[GraphSnapshot, ...]:
    """Law A's graph: only the published link becomes an ECHOED_BY edge."""
    published = next(link for link in links if link.link_id == "link:a-am1-makers")
    final_logs = "art:32099R0001:article-6-1"
    nodes = (
        _node(LAW_A, "procedure", "Fixture Regulation on widget safety"),
        _node(MAKERS, "actor", "Widget Makers Europe"),
        _node(MEP_ONE, "actor", "Alex Example"),
        _node("ask:a-makers", "ask", "Keep logs for at least six months"),
        _node(AM1, "amendment", "IMCO amendment 101"),
        _node(final_logs, "article", "Article 6(1)"),
    )
    edges = (
        GraphEdge(
            edge_id="edge:requested:a-makers",
            relation="REQUESTED",
            source=MAKERS,
            target="ask:a-makers",
            dated_on=date(2099, 2, 1),
        ),
        GraphEdge(
            edge_id="edge:echoed:a-am1-makers",
            relation="ECHOED_BY",
            source="ask:a-makers",
            target=AM1,
            spans=(*published.ask_spans, *published.amendment_spans),
            link_id=published.link_id,
            dated_on=date(2099, 4, 1),
        ),
        GraphEdge(
            edge_id="edge:tabled:a-am1-mep1",
            relation="TABLED_BY",
            source=AM1,
            target=MEP_ONE,
            dated_on=date(2099, 4, 1),
        ),
        GraphEdge(
            edge_id="edge:realized:a-makers",
            relation="REALIZED_IN",
            source="ask:a-makers",
            target=final_logs,
            spans=(_article_span(final_logs, "for at least six months"),),
            outcome_id="outcome:a-ask-makers-final",
            dated_on=date(2099, 11, 30),
        ),
        GraphEdge(edge_id="edge:about:a-am1", relation="ABOUT", source=AM1, target=LAW_A),
    )
    return (
        GraphSnapshot(
            snapshot_id="snapshot:fixture-a",
            run_id="run:fixture-a",
            generated_at=RETRIEVED,
            procedure_ids=(LAW_A,),
            nodes=nodes,
            edges=edges,
            coverage={LAW_A: _coverage_a()},
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


def build_fixture() -> AtlasFixture:
    passages = _passages()
    links = _links()
    return AtlasFixture(
        laws=_laws(),
        documents=_documents(),
        document_texts=tuple(
            DocumentText(document_id=doc, text=text) for doc, text in TEXTS.items()
        ),
        actors=_actors(),
        passages=passages,
        amendments=_amendments(),
        articles=_articles(),
        asks=_asks(passages),
        candidates=_candidates(),
        links=links,
        outcomes=_outcomes(),
        positions=_positions(),
        forecasts=_forecasts(),
        graphs=_graphs(links),
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
    (directory / "cases.json").write_text(
        json.dumps(CASES, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    write_fixture(FIXTURE_DIRECTORY)
    print(f"Wrote the Atlas fixture to {FIXTURE_DIRECTORY}")
