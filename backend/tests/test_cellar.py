"""CELLAR connector: identifiers by SPARQL, acts by content negotiation, provision splitting.

Every response below is a trimmed copy of what the real service returned on 3 October 2026.
"""

import hashlib
import json
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest
from extraction_fixtures import FETCHED_AT

from influence.extraction.cache import HttpCache
from influence.extraction.fetching import CachedFetcher, FetchError, RateLimiter, RawResponse
from influence.repositories import cellar
from influence.repositories.cellar import CellarError, FetchedAct, MissingAct

AI_ACT = "2021/0106(COD)"
XHTML = "application/xhtml+xml;charset=UTF-8"
CELEX_BASE = "http://publications.europa.eu/resource/celex/"
STREAM_BASE = "http://publications.europa.eu/resource/cellar/e0649735.0001.03/"


@dataclass
class ScriptedFetcher:
    """Answers the first script entry whose text occurs in the decoded URL.

    SPARQL queries travel URL-encoded, so a test names a fragment of the query rather
    than the whole address. An unscripted URL is a host that does not answer.
    """

    script: list[tuple[str, RawResponse]]
    calls: list[str] = field(default_factory=list[str])
    headers: list[Mapping[str, str] | None] = field(default_factory=list[Mapping[str, str] | None])

    def __call__(self, url: str, headers: Mapping[str, str] | None = None) -> RawResponse:
        decoded = urllib.parse.unquote_plus(url)
        self.calls.append(decoded)
        self.headers.append(headers)
        for fragment, response in self.script:
            if fragment in decoded:
                return response
        raise FetchError(url, "No response: unscripted")


def fetcher_for(
    tmp_path: Path, script: list[tuple[str, RawResponse]]
) -> tuple[CachedFetcher, ScriptedFetcher]:
    scripted = ScriptedFetcher(script)
    return (
        CachedFetcher(
            cache=HttpCache(tmp_path),
            fetcher=scripted,
            limiter=RateLimiter(monotonic=lambda: 0.0, sleep=lambda _: None),
            clock=lambda: FETCHED_AT,
        ),
        scripted,
    )


def sparql(*rows: dict[str, str]) -> RawResponse:
    bindings = [
        {name: {"type": "literal", "value": value} for name, value in row.items()} for row in rows
    ]
    body: dict[str, object] = {
        "head": {"link": [], "vars": []},
        "results": {"distinct": False, "bindings": bindings},
    }
    return RawResponse(200, "application/sparql-results+json", json.dumps(body).encode())


# --- Identifiers ------------------------------------------------------------------------


def test_a_completed_procedure_resolves_to_its_proposal_final_act_and_com_number(
    tmp_path: Path,
) -> None:
    fetcher, scripted = fetcher_for(
        tmp_path, [("procedure/2021_106>", sparql({"final": "32024R1689", "prop": "52021PC0206"}))]
    )
    law = cellar.resolve_celex(fetcher, AI_ACT)
    assert law == cellar.LawIdentifiers(
        procedure_id=AI_ACT,
        celex_proposal="52021PC0206",
        celex_final="32024R1689",
        com_reference="COM(2021)206",
        proposal_candidates=("52021PC0206",),
        final_candidates=("32024R1689",),
        ambiguous=False,
    )
    assert scripted.calls[0].startswith(cellar.SPARQL_ENDPOINT + "?query=PREFIX cdm:")
    assert scripted.headers == [{"Accept": "application/sparql-results+json"}]
    cellar.resolve_celex(fetcher, AI_ACT)
    assert len(scripted.calls) == 1
    cellar.resolve_celex(fetcher, AI_ACT, refresh=True)
    assert len(scripted.calls) == 2


def test_an_ongoing_procedure_has_a_proposal_and_no_final_act(tmp_path: Path) -> None:
    fetcher, _ = fetcher_for(tmp_path, [("procedure/2025_59>", sparql({"prop": "52025PC0101"}))])
    law = cellar.resolve_celex(fetcher, "2025/0059(COD)")
    assert (law.celex_proposal, law.celex_final, law.final_candidates) == ("52025PC0101", None, ())
    assert not law.ambiguous


def test_a_procedure_cellar_does_not_know_resolves_to_nothing_rather_than_failing(
    tmp_path: Path,
) -> None:
    fetcher, _ = fetcher_for(tmp_path, [("procedure/2031_1>", sparql())])
    law = cellar.resolve_celex(fetcher, "2031/0001(COD)")
    assert (law.celex_proposal, law.celex_final, law.com_reference) == (None, None, None)
    assert not law.ambiguous


def test_several_final_acts_are_all_listed_and_none_is_chosen(tmp_path: Path) -> None:
    rows = [
        {"final": "32024R1624", "prop": "52021PC0420"},
        {"final": "32024L1640", "prop": "52021PC0420"},
    ]
    fetcher, _ = fetcher_for(tmp_path, [("procedure/2021_239>", sparql(*rows))])
    law = cellar.resolve_celex(fetcher, "2021/0239(COD)")
    assert law.celex_final is None
    assert law.final_candidates == ("32024L1640", "32024R1624")
    assert law.ambiguous
    assert law.celex_proposal == "52021PC0420"


def test_a_corrigendum_is_listed_but_does_not_make_the_act_ambiguous(tmp_path: Path) -> None:
    rows = [{"final": "32016R0679"}, {"final": "32016R0679R(02)"}]
    fetcher, _ = fetcher_for(tmp_path, [("procedure/2012_11>", sparql(*rows))])
    law = cellar.resolve_celex(fetcher, "2012/0011(COD)")
    assert law.celex_final == "32016R0679"
    assert law.final_candidates == ("32016R0679", "32016R0679R(02)")
    assert not law.ambiguous


def test_several_proposals_are_ambiguous_and_give_no_com_number(tmp_path: Path) -> None:
    rows = [{"prop": "52021PC0206"}, {"prop": "52021PC0207"}]
    fetcher, _ = fetcher_for(tmp_path, [("procedure/2021_106>", sparql(*rows))])
    law = cellar.resolve_celex(fetcher, AI_ACT)
    assert (law.celex_proposal, law.com_reference, law.ambiguous) == (None, None, True)


def test_only_a_commission_proposal_has_a_com_number() -> None:
    assert cellar.com_reference("52021PC0206") == "COM(2021)206"
    assert cellar.com_reference("52021JC0001") is None
    assert cellar.com_reference(None) is None


def test_a_malformed_procedure_reference_is_refused_before_any_request(tmp_path: Path) -> None:
    fetcher, scripted = fetcher_for(tmp_path, [])
    with pytest.raises(CellarError, match="Not a procedure reference"):
        cellar.resolve_celex(fetcher, "2021/106")
    assert scripted.calls == []
    assert cellar.procedure_uri(AI_ACT).endswith("/procedure/2021_106")


def test_an_unreachable_or_unreadable_sparql_endpoint_is_one_explicit_error(
    tmp_path: Path,
) -> None:
    silent, _ = fetcher_for(tmp_path / "silent", [])
    with pytest.raises(CellarError, match="SPARQL request failed: No response"):
        cellar.resolve_celex(silent, AI_ACT)
    html = RawResponse(200, "text/html", b"<html>Virtuoso error</html>")
    garbled, _ = fetcher_for(tmp_path / "garbled", [("procedure/2021_106>", html)])
    with pytest.raises(CellarError, match="not a SELECT result"):
        cellar.resolve_celex(garbled, AI_ACT)


def test_a_celex_number_maps_back_to_its_procedure_with_the_procedure_type(
    tmp_path: Path,
) -> None:
    fetcher, scripted = fetcher_for(
        tmp_path, [('STR(?c) = "32024R1689"', sparql({"ref": "2021/0106/COD"}))]
    )
    assert cellar.procedure_for_celex(fetcher, "32024R1689") == AI_ACT
    assert "procedure_code_interinstitutional_reference_procedure" in scripted.calls[0]


def test_a_celex_in_several_or_no_dossiers_has_no_single_procedure(tmp_path: Path) -> None:
    rows = [{"ref": "2016/0280/COD"}, {"ref": "2021/0106/COD"}, {"ref": "not a reference"}]
    fetcher, _ = fetcher_for(
        tmp_path,
        [('"32019L0790"', sparql(*rows)), ('"39999R9999"', sparql())],
    )
    assert cellar.procedures_for_celex(fetcher, "32019L0790") == ("2016/0280(COD)", AI_ACT)
    assert cellar.procedure_for_celex(fetcher, "32019L0790") is None
    assert cellar.procedure_for_celex(fetcher, "39999R9999") is None


def test_text_that_is_not_a_celex_never_reaches_a_query_or_a_url(tmp_path: Path) -> None:
    fetcher, scripted = fetcher_for(tmp_path, [])
    injection = '32024R1689") } DROP'
    with pytest.raises(CellarError, match="Not a CELEX number"):
        cellar.procedure_for_celex(fetcher, injection)
    with pytest.raises(CellarError, match="Not a CELEX number"):
        cellar.fetch_act(fetcher, "../procedure/2021_106")
    assert scripted.calls == []


def test_parliament_positions_are_the_adopted_texts_filed_in_the_dossier(tmp_path: Path) -> None:
    rows = [
        {"celex": "52021PC0206"},
        {"celex": "52024AP0138"},
        {"celex": "32024R1689"},
        {"celex": "52021AE2482"},
    ]
    fetcher, scripted = fetcher_for(tmp_path, [("dossier_contains_work", sparql(*rows))])
    assert cellar.resolve_position_celex(fetcher, AI_ACT) == ("52024AP0138",)
    assert "procedure/2021_106>" in scripted.calls[0]


# --- Fetching an act --------------------------------------------------------------------

LISTING = (
    "<html><head><title>300 Multiple-Choice Response</title></head><body> List of URI's:<ul>"
    '<li title="manifestation">cellar:e0649735.0001.03<ul>'
    f'<li title="item"><a href="{STREAM_BASE}DOC_3"><span class="url">(DOC_3)</span></a><ul>'
    '<li title="stream_name">1_EN_annexe_proposition_part1_v7.html</li>'
    '<li title="stream_label">act</li><li title="stream_order" id="streamOrder">3</li></ul></li>'
    f'<li title="item"><a href="{STREAM_BASE}DOC_2"><span class="url">(DOC_2)</span></a><ul>'
    '<li title="stream_name">1_EN_ACT_part2_v7.html</li>'
    '<li title="stream_label">act</li><li title="stream_order" id="streamOrder">2</li></ul></li>'
    f'<li title="item"><a href="{STREAM_BASE}DOC_1"><span class="url">(DOC_1)</span></a><ul>'
    '<li title="stream_name">1_EN_ACT_part1_v7.html</li>'
    '<li title="stream_label">act</li><li title="stream_order" id="streamOrder">1</li></ul></li>'
    "</ul></li></ul></body></html>"
).encode()


def test_a_final_act_is_fetched_as_xhtml_with_what_a_citation_needs(tmp_path: Path) -> None:
    body = b"<html><body><p>act</p></body></html>"
    fetcher, scripted = fetcher_for(
        tmp_path, [(CELEX_BASE + "32024R1689", RawResponse(200, XHTML, body))]
    )
    act = cellar.fetch_act(fetcher, "32024R1689")
    assert act == FetchedAct(
        celex="32024R1689",
        url=CELEX_BASE + "32024R1689",
        language="eng",
        retrieved_at=FETCHED_AT,
        sha256=hashlib.sha256(body).hexdigest(),
        media_type=XHTML,
        body=body,
    )
    assert scripted.headers == [
        {"Accept": "application/xhtml+xml, text/html;q=0.9", "Accept-Language": "eng"}
    ]
    assert "body=" not in repr(act)


def test_another_language_is_negotiated_and_cached_apart(tmp_path: Path) -> None:
    fetcher, scripted = fetcher_for(
        tmp_path, [(CELEX_BASE + "32024R1689", RawResponse(200, XHTML, b"<p>x</p>"))]
    )
    cellar.fetch_act(fetcher, "32024R1689")
    spanish = cellar.fetch_act(fetcher, "32024R1689", language="spa")
    assert isinstance(spanish, FetchedAct)
    assert spanish.language == "spa"
    assert [headers and headers["Accept-Language"] for headers in scripted.headers] == [
        "eng",
        "spa",
    ]


def test_a_proposal_answers_with_a_list_of_streams_and_the_act_stream_is_followed(
    tmp_path: Path,
) -> None:
    fetcher, scripted = fetcher_for(
        tmp_path,
        [
            (CELEX_BASE + "52021PC0206", RawResponse(300, XHTML, LISTING)),
            (STREAM_BASE + "DOC_1", RawResponse(200, XHTML, b"<p>Proposal for a</p>")),
            (STREAM_BASE + "DOC_3", RawResponse(200, XHTML, b"<p>ANNEX I</p>")),
        ],
    )
    act = cellar.fetch_act(fetcher, "52021PC0206")
    assert isinstance(act, FetchedAct)
    assert (act.url, act.body) == (STREAM_BASE + "DOC_1", b"<p>Proposal for a</p>")
    assert (act.annexes, act.annex_gaps) == ((b"<p>ANNEX I</p>",), ())
    assert scripted.calls == [
        CELEX_BASE + "52021PC0206",
        STREAM_BASE + "DOC_1",
        STREAM_BASE + "DOC_3",
    ]
    assert cellar.act_stream_url(LISTING) == STREAM_BASE + "DOC_1"
    assert cellar.annex_stream_urls(LISTING) == (STREAM_BASE + "DOC_3",)
    # The digest covers every stream the text came from, in order.
    assert act.sha256 == hashlib.sha256(b"<p>Proposal for a</p><p>ANNEX I</p>").hexdigest()


def test_annex_streams_are_taken_in_their_stream_order(tmp_path: Path) -> None:
    second = LISTING.replace(b"1_EN_ACT_part2", b"2_EN_annexe_proposition_part2")
    assert cellar.annex_stream_urls(second) == (STREAM_BASE + "DOC_2", STREAM_BASE + "DOC_3")


def test_a_lost_annex_stream_is_recorded_and_does_not_lose_the_act(tmp_path: Path) -> None:
    fetcher, _ = fetcher_for(
        tmp_path,
        [
            (CELEX_BASE + "52021PC0206", RawResponse(300, XHTML, LISTING)),
            (STREAM_BASE + "DOC_1", RawResponse(200, XHTML, b"<p>Proposal for a</p>")),
        ],
    )
    act = cellar.fetch_act(fetcher, "52021PC0206")
    assert isinstance(act, FetchedAct)
    assert act.annexes == ()
    assert act.annex_gaps == (STREAM_BASE + "DOC_3: No response: unscripted",)
    assert act.sha256 == hashlib.sha256(b"<p>Proposal for a</p>").hexdigest()


def test_a_list_with_no_recognisable_act_stream_is_a_failure_with_its_reason(
    tmp_path: Path,
) -> None:
    listing = LISTING.replace(b"_ACT_", b"_annexe_")
    fetcher, _ = fetcher_for(
        tmp_path, [(CELEX_BASE + "52021PC0206", RawResponse(300, XHTML, listing))]
    )
    gap = cellar.fetch_act(fetcher, "52021PC0206")
    assert isinstance(gap, MissingAct)
    assert (gap.status, gap.http_status) == ("failed", 300)
    assert "none is recognisable as the act" in gap.reason


def test_a_celex_cellar_does_not_hold_is_a_typed_gap_not_an_exception(tmp_path: Path) -> None:
    fetcher, _ = fetcher_for(
        tmp_path, [(CELEX_BASE + "39999R9999", RawResponse(404, None, b"not found"))]
    )
    assert cellar.fetch_act(fetcher, "39999R9999") == MissingAct(
        celex="39999R9999",
        url=CELEX_BASE + "39999R9999",
        language="eng",
        status="missing",
        reason="HTTP 404",
        http_status=404,
    )


def test_a_broken_request_is_told_apart_from_a_missing_document(tmp_path: Path) -> None:
    fetcher, _ = fetcher_for(
        tmp_path,
        [
            (CELEX_BASE + "32024R1689", RawResponse(503, None, b"busy")),
            (CELEX_BASE + "52021PC0206", RawResponse(300, XHTML, LISTING)),
        ],
    )
    busy = cellar.fetch_act(fetcher, "32024R1689")
    assert isinstance(busy, MissingAct)
    assert (busy.status, busy.http_status) == ("failed", 503)
    # The list arrived, the stream it names did not: the gap names the stream.
    lost = cellar.fetch_act(fetcher, "52021PC0206")
    assert isinstance(lost, MissingAct)
    assert (lost.status, lost.url, lost.http_status) == ("failed", STREAM_BASE + "DOC_1", None)


def test_the_source_record_cites_the_act_and_stays_undated_unless_told(tmp_path: Path) -> None:
    fetcher, _ = fetcher_for(
        tmp_path, [(CELEX_BASE + "32024R1689", RawResponse(200, XHTML, b"<p>act</p>"))]
    )
    act = cellar.fetch_act(fetcher, "32024R1689")
    assert isinstance(act, FetchedAct)
    record = cellar.source_document(
        act, procedure_id=AI_ACT, extraction_status="extracted", text_characters=3
    )
    assert record.document_id == cellar.cellar_document_id("32024R1689") == "doc:cellar:32024R1689"
    assert (record.source_kind, record.url) == ("cellar", CELEX_BASE + "32024R1689")
    assert (record.published_at, record.retrieved_at) == (None, FETCHED_AT)
    assert record.sha256 == act.sha256
    assert record.reuse_terms == "Commission reuse policy, CC BY 4.0 (Decision 2011/833/EU)"
    assert (record.media_type, record.language, record.text_characters) == (XHTML, "eng", 3)
    dated = cellar.source_document(
        act,
        procedure_id=None,
        extraction_status="partial",
        text_characters=None,
        title="Artificial Intelligence Act",
        published_at=FETCHED_AT,
    )
    assert (dated.published_at, dated.title, dated.procedure_id) == (
        FETCHED_AT,
        "Artificial Intelligence Act",
        None,
    )


# --- Provisions -------------------------------------------------------------------------

# The Official Journal layout of 32024R1689: ELI subdivision ids, numbers in table cells,
# footnote calls as anchors, paragraphs as "1.   text", an annex in its own container.
OFFICIAL_JOURNAL = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head>
  <meta http-equiv="content-type" content="text/html; charset=utf-8"/>
  <title>L_202401689EN.000101.fmx.xml</title></head>
<body>
  <table><col width="20%"/><tbody><tr><td/><td><p class="oj-hd-uniq">2024/1689</p></td>
    <td><p class="oj-hd-date">12.7.2024</p></td></tr></tbody></table>
  <hr class="oj-separator"/>
  <div class="eli-container">
    <div class="eli-main-title" id="tit_1"><p class="oj-doc-ti">REGULATION (EU) 2024/1689</p></div>
    <div class="eli-subdivision" id="pbl_1">
      <p class="oj-normal">Whereas:</p>
      <div class="eli-subdivision" id="rct_1">
        <table><tbody><tr><td><p class="oj-normal">(1)</p></td>
          <td><p class="oj-normal">The purpose of this Regulation is to improve the
            functioning of the internal&#160;market <a id="ntc5-L_1" href="#ntr5-L_1"
              >(<span class="oj-super oj-note-tag">5</span>)</a>, in accordance with Union
            values.</p></td></tr></tbody></table>
      </div>
      <div class="eli-subdivision" id="rct_2">
        <table><tbody><tr><td><p class="oj-normal">(2)</p></td>
          <td><p class="oj-normal">This Regulation should be applied in accordance with
            the <a href="#anx_I">values</a> of the Union.</p></td></tr></tbody></table>
      </div>
    </div>
    <div class="eli-subdivision" id="enc_1">
      <div id="cpt_I"><p class="oj-ti-section-1">CHAPTER I</p>
        <div class="eli-subdivision" id="art_4">
          <p id="d1e2795-1-1" class="oj-ti-art">Article 4</p>
          <div class="eli-title" id="art_4.tit_1"><p class="oj-sti-art">AI literacy</p></div>
          <p class="oj-normal">Providers and deployers of AI systems shall take measures
            to ensure a sufficient level of AI literacy of their staff.</p>
        </div>
        <div class="eli-subdivision" id="art_5">
          <p class="oj-ti-art">Article 5</p>
          <div class="eli-title" id="art_5.tit_1">
            <p class="oj-sti-art">Prohibited AI practices</p></div>
          <div id="005.001">
            <p class="oj-normal">1.   The following AI practices shall be prohibited:</p>
            <table><tbody><tr><td><p class="oj-normal">(a)</p></td>
              <td><p class="oj-normal">the placing on the market of an AI system that
                deploys subliminal techniques;</p></td></tr></tbody></table>
          </div>
          <div id="005.002">
            <p class="oj-normal">2.   The use of such systems shall comply with the
              following:</p>
            <p class="oj-normal">1.   a quoted paragraph that restarts numbering stays here.</p>
          </div>
        </div>
      </div>
    </div>
    <div class="eli-subdivision" id="fnp_1">
      <p class="oj-normal">This Regulation shall be binding in its entirety.</p>
    </div>
  </div>
  <div class="eli-container" id="anx_I">
    <p class="oj-doc-ti">ANNEX I</p>
    <p class="oj-normal">List of Union harmonisation legislation</p>
  </div>
</body></html>
"""

# The "v7" Word export of 52021PC0206: no ids, numbers in <span class="num"> with no space,
# an explanatory memorandum before the act and a financial statement after it.
PROPOSAL = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>1_EN_ACT_part1_v7.docx</title></head>
<body><div class="contentWrapper"><div class="content">
  <p class="Typedudocument_cp"><span>EXPLANATORY MEMORANDUM</span></p>
  <p class="li ManualNumPar1"><span class="num"><span>(1)</span></span><span>A memorandum point
    that looks like a recital.</span></p>
  <p class="Typedudocument"><span>Proposal for a REGULATION</span></p>
  <p class="Normal"><span>Whereas:</span></p>
  <p class="Normal"><span>An unnumbered sentence before the first recital.</span></p>
  <p class="li ManualConsidrant"><span class="num"><span>(1)</span></span><span>The purpose of
    this Regulation is to improve the functioning of the internal market</span><span
    class="FootnoteReference">
      <a class="footnoteRef" id="footnoteref39" href="#footnote39">38</a>
    </span><span> by laying down a uniform legal framework.</span></p>
  <p class="Normal"><span>It continues in a second subparagraph.</span></p>
  <p class="li ManualConsidrant"><span class="num"><span>(2)</span></span><span>Artificial
    intelligence is a fast evolving family of technologies.</span></p>
  <p class="li ManualConsidrant"><span class="num"><span>(2)</span></span><span>A repeated
    number does not open a second recital.</span></p>
  <p class="Formuledadoption"><span>HAVE ADOPTED THIS REGULATION:</span></p>
  <p class="Normal"><span>(3) A numbered line after the enacting formula is no recital.</span></p>
  <p class="SectionTitle"><span>TITLE I</span></p>
  <p class="Titrearticle"><span>Article 1</span><span><br/>Subject matter</span></p>
  <p class="Normal"><span>This Regulation lays down:</span></p>
  <p class="li Point1"><span class="num"><span>(a)</span></span><span>harmonised rules for
    the placing on the market of AI systems;</span></p>
  <p class="SectionTitle"><span>TITLE II</span></p>
  <p class="Titrearticle"><span>Article 2</span></p>
  <p class="Articletitle"><span>Scope</span></p>
  <p class="Normal"><span>This Regulation is without prejudice to other acts.</span></p>
  <p class="li ManualNumPar1"><span class="num"><span>1.</span></span><span>This Regulation
    applies to providers.</span></p>
  <p class="li ManualNumPar1"><span class="num"><span>2.</span></span><span>In Regulation
    (EU) 2018/858 the following Article is replaced:</span></p>
  <p class="Normal"><span>Article 2</span></p>
  <p class="Normal"><span>The quoted article stays inside the paragraph quoting it.</span></p>
  <p class="Normal"><span>Done at Brussels,</span></p>
  <p class="Titrearticle"><span>Article 3</span></p>
  <p class="Normal"><span>LEGISLATIVE FINANCIAL STATEMENT</span></p>
</div></div></body></html>
"""


def split(
    markup: bytes, *, celex: str = "32024R1689", version_date: date | None = None
) -> cellar.SplitProvisions:
    return cellar.split_provisions(
        markup,
        procedure_id=AI_ACT,
        celex=celex,
        stage="final_act",
        document_id=cellar.cellar_document_id(celex),
        version_date=version_date,
    )


def test_an_official_journal_act_splits_on_its_eli_subdivisions() -> None:
    result = split(OFFICIAL_JOURNAL)
    assert [(item.provision, item.kind) for item in result.provisions] == [
        ("Recital 1", "recital"),
        ("Recital 2", "recital"),
        ("Article 4", "article"),
        ("Article 5(1)", "paragraph"),
        ("Article 5(2)", "paragraph"),
        ("Annex I", "annex"),
    ]
    assert [item.article_id for item in result.provisions] == [
        "art:32024R1689:recital-1",
        "art:32024R1689:recital-2",
        "art:32024R1689:article-4",
        "art:32024R1689:article-5-1",
        "art:32024R1689:article-5-2",
        "art:32024R1689:annex-i",
    ]
    texts = {item.provision: item.text for item in result.provisions}
    # The number cell, the footnote call and the layout whitespace are all gone.
    assert texts["Recital 1"] == (
        "The purpose of this Regulation is to improve the functioning of the internal "
        "market, in accordance with Union values."
    )
    # An ordinary link is text; only a footnote call is dropped.
    assert texts["Recital 2"].endswith("in accordance with the values of the Union.")
    assert texts["Article 4"] == (
        "Providers and deployers of AI systems shall take measures to ensure a sufficient "
        "level of AI literacy of their staff."
    )
    assert texts["Article 5(1)"] == (
        "The following AI practices shall be prohibited:\n"
        "(a) the placing on the market of an AI system that deploys subliminal techniques;"
    )
    assert texts["Article 5(2)"] == (
        "The use of such systems shall comply with the following:\n"
        "1. a quoted paragraph that restarts numbering stays here."
    )
    assert texts["Annex I"] == "ANNEX I\nList of Union harmonisation legislation"
    assert result.reason is None


def test_every_provision_is_a_substring_of_the_document_text_and_shares_its_keys() -> None:
    result = split(OFFICIAL_JOURNAL)
    document = result.document_text
    assert document.document_id == "doc:cellar:32024R1689"
    assert "L_202401689EN" not in document.text
    assert "Whereas:\n(1) The purpose" in document.text
    assert "CHAPTER I\nArticle 4\nAI literacy\nProviders" in document.text
    assert document.text.endswith("ANNEX I\nList of Union harmonisation legislation")
    for item in result.provisions:
        assert item.text in document.text
        assert (item.procedure_id, item.document_id, item.stage) == (
            AI_ACT,
            document.document_id,
            "final_act",
        )


def test_the_official_journal_date_dates_the_version_unless_the_caller_knows_better() -> None:
    stated = split(OFFICIAL_JOURNAL)
    assert stated.published_on == date(2024, 7, 12)
    assert {item.version_date for item in stated.provisions} == {date(2024, 7, 12)}
    given = split(OFFICIAL_JOURNAL, version_date=date(2024, 8, 1))
    assert {item.version_date for item in given.provisions} == {date(2024, 8, 1)}
    impossible = split(OFFICIAL_JOURNAL.replace(b"12.7.2024", b"31.2.2024"))
    assert impossible.published_on is None
    assert {item.version_date for item in impossible.provisions} == {None}


def test_a_proposal_without_ids_is_split_on_its_english_headings() -> None:
    result = split(PROPOSAL, celex="52021PC0206")
    assert [(item.provision, item.kind) for item in result.provisions] == [
        ("Recital 1", "recital"),
        ("Recital 2", "recital"),
        ("Article 1", "article"),
        ("Article 2", "article"),
        ("Article 2(1)", "paragraph"),
        ("Article 2(2)", "paragraph"),
    ]
    texts = {item.provision: item.text for item in result.provisions}
    assert texts["Recital 1"] == (
        "The purpose of this Regulation is to improve the functioning of the internal market "
        "by laying down a uniform legal framework.\nIt continues in a second subparagraph."
    )
    assert texts["Recital 2"] == (
        "Artificial intelligence is a fast evolving family of technologies.\n"
        "(2) A repeated number does not open a second recital."
    )
    # The article title and the division heading that follows are not the article's text.
    assert texts["Article 1"] == (
        "This Regulation lays down:\n"
        "(a) harmonised rules for the placing on the market of AI systems;"
    )
    assert texts["Article 2"] == "This Regulation is without prejudice to other acts."
    assert texts["Article 2(1)"] == "This Regulation applies to providers."
    assert texts["Article 2(2)"] == (
        "In Regulation (EU) 2018/858 the following Article is replaced:\n"
        "Article 2\nThe quoted article stays inside the paragraph quoting it."
    )
    assert result.provisions[0].article_id == "art:52021PC0206:recital-1"
    assert (result.published_on, result.reason) == (None, None)
    assert {item.version_date for item in result.provisions} == {None}
    assert "Article 1\nSubject matter" in result.document_text.text
    for item in result.provisions:
        assert item.text in result.document_text.text


# The "v7" Word export of the 52021PC0206 annex stream: a cover page that names the annexes,
# then one "ANNEX N" heading per annex with its title after a line break.
PROPOSAL_ANNEXES = b"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>2_EN_annexe_proposition_part1_v7</title>
</head><body><div class="contentWrapper"><div class="content">
  <p class="Typedudocument_cp"><span>ANNEXES</span></p>
  <p class="Titreobjet_cp"><span>to the Proposal for a Regulation laying down harmonised
    rules on artificial intelligence</span></p>
  <p class="Annexetitre"><span>ANNEX I</span><span><br/>ARTIFICIAL INTELLIGENCE TECHNIQUES
    AND APPROACHES</span></p>
  <p class="li Point0"><span class="num"><span>(a)</span></span><span>Machine learning
    approaches, as referred to in Annex III;</span></p>
  <p class="Annexetitre"><span>ANNEX III</span></p>
  <p class="Normal"><span>High-risk AI systems</span></p>
</div></div></body></html>
"""


def test_a_proposals_annex_streams_follow_its_act_and_split_one_provision_per_annex() -> None:
    result = cellar.split_provisions(
        PROPOSAL,
        procedure_id=AI_ACT,
        celex="52021PC0206",
        stage="proposal",
        document_id=cellar.cellar_document_id("52021PC0206"),
        version_date=None,
        annexes=(PROPOSAL_ANNEXES,),
    )
    annexes = [item for item in result.provisions if item.kind == "annex"]
    assert [(item.provision, item.article_id) for item in annexes] == [
        ("Annex I", "art:52021PC0206:annex-i"),
        ("Annex III", "art:52021PC0206:annex-iii"),
    ]
    # The cover page ("ANNEXES") opens nothing; a cross-reference ("Annex III") neither.
    assert annexes[0].text == (
        "ANNEX I\nARTIFICIAL INTELLIGENCE TECHNIQUES AND APPROACHES\n"
        "(a) Machine learning approaches, as referred to in Annex III;"
    )
    assert annexes[1].text == "ANNEX III\nHigh-risk AI systems"
    # The act's provisions come first and are unchanged.
    assert [item.provision for item in result.provisions[:2]] == ["Recital 1", "Recital 2"]
    assert result.document_text.text.endswith("ANNEX III\nHigh-risk AI systems")
    for item in result.provisions:
        assert item.text in result.document_text.text
    assert result.annex_reasons == ()


def test_an_annex_stream_with_no_heading_is_kept_as_text_and_says_why() -> None:
    bare = b"<html><body><p>ANNEX</p><p>One annex.</p></body></html>"
    unheaded = b"<html><body><p>ANNEXES</p><p>A cover page only.</p></body></html>"
    result = cellar.split_provisions(
        PROPOSAL,
        procedure_id=AI_ACT,
        celex="52021PC0206",
        stage="proposal",
        document_id=cellar.cellar_document_id("52021PC0206"),
        version_date=None,
        annexes=(bare, unheaded, b""),
    )
    assert [item.provision for item in result.provisions if item.kind == "annex"] == ["Annex"]
    assert "A cover page only." in result.document_text.text
    # An empty stream has nothing to split and is not reported.
    assert result.annex_reasons == (f"52021PC0206 annex stream 2: {cellar.NO_ANNEX_HEADING}",)


def test_an_annex_stream_that_is_not_utf8_is_an_error_naming_the_stream() -> None:
    with pytest.raises(CellarError, match="52021PC0206 annex stream 1 is not UTF-8"):
        cellar.split_provisions(
            PROPOSAL,
            procedure_id=AI_ACT,
            celex="52021PC0206",
            stage="proposal",
            document_id=cellar.cellar_document_id("52021PC0206"),
            version_date=None,
            annexes=(b"\xff\xfe",),
        )


def test_text_with_no_recognisable_structure_yields_no_provisions_and_says_why() -> None:
    resolution = (
        b"<html><body><div class='eli-main-title' id='tit_1'><p>P9_TA(2024)0138</p>"
        b"<p>European Parliament legislative resolution<br>of 13 March 2024</p></div>"
        b"<p>1. Adopts its position at first reading;</body></html>"
    )
    result = split(resolution, celex="52024AP0138")
    assert result.provisions == ()
    assert result.reason == cellar.NO_STRUCTURE
    assert result.document_text.text == (
        "P9_TA(2024)0138\nEuropean Parliament legislative resolution\nof 13 March 2024\n"
        "1. Adopts its position at first reading;"
    )


def test_sloppy_markup_is_read_without_raising_and_without_inventing_text() -> None:
    sloppy = (
        b"<html><head><style>p { color: red }</style></head><body>"
        b"<div id='art_5a'><p>Stray close</span></i> and an <b>unclosed bold</p></div>"
        b"<div id='art_5A'><p>Same label in another case</p></div>"
        b"<script>alert(1)</script>Trailing text"
    )
    result = split(sloppy)
    assert [(item.article_id, item.text) for item in result.provisions] == [
        ("art:32024R1689:article-5a", "Stray close and an unclosed bold"),
        ("art:32024R1689:article-5a-2", "Same label in another case"),
    ]
    assert result.document_text.text.endswith("Same label in another case\nTrailing text")
    assert "alert" not in result.document_text.text
    assert "color" not in result.document_text.text


def test_bytes_that_are_not_utf8_are_an_explicit_error() -> None:
    with pytest.raises(CellarError, match="52021PC0206 is not UTF-8"):
        split(b"<p>caf\xe9</p>", celex="52021PC0206")
