"""Part 1 · Collect on a tiny public record: every layer, every gap, every way to stop.

The world below is written in the real formats (Parltrack dump lines, the register export,
Have Your Say JSON, CELLAR XHTML) using the connector tests' own builders, and answered by
a scripted fetcher: no test reaches the network.
"""

import logging
import urllib.parse
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_cellar import (
    CELEX_BASE,
    LISTING,
    OFFICIAL_JOURNAL,
    PROPOSAL,
    PROPOSAL_ANNEXES,
    STREAM_BASE,
    XHTML,
    ScriptedFetcher,
    sparql,
)
from test_hys import as_json, feedback, feedback_page, initiative, make_pdf, search_page
from test_parltrack import (
    ai_act_dossier,
    committee_record,
    dossier,
    mep_record,
    switcher,
    write_dump,
)
from test_register import export, representative

from influence import cli
from influence.extraction.cache import HttpCache
from influence.extraction.fetching import CachedFetcher, RateLimiter, RawResponse
from influence.extraction.records import StageStore, read_records
from influence.repositories import hys
from influence.schemas.atlas import (
    CITIZENS_ACTOR_ID,
    Actor,
    Amendment,
    ArticleVersion,
    DocumentText,
    LawRecord,
    Layer,
    LayerCoverage,
    LayerStatus,
    Passage,
    RunManifest,
    SourceDocument,
    span_matches,
)
from influence.services import collect
from influence.services.collect import (
    AmbiguousLawError,
    CollectError,
    CollectInputs,
    CollectResult,
    CollectSettings,
)

AI_ACT = "2021/0106(COD)"
ONGOING = "2024/0100(COD)"
NEWER_THAN_DUMP = "2025/0059(COD)"
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
LATER = "2026/0001(COD)"
RECENT = "2026-09-01T00:00:00"
EQUINET = "718971811339-46"
ATTACHMENT = "090166e5e1cd1796"

type Script = list[tuple[str, RawResponse]]

FEEDBACK = [
    feedback(1),
    feedback(
        2, organization="Acme Unknown Lobby", trNumber=None, userType="COMPANY", attachments=[]
    ),
    feedback(
        3,
        feedback="I support strict rules for AI.",
        userType="EU_CITIZEN",
        organization=None,
        trNumber=None,
        attachments=[],
    ),
]
PDF = make_pdf(("We ask for a notice period of at least six months.",))


def ai_act_script() -> Script:
    return [
        ("procedure/2021_106>", sparql({"final": "32024R1689", "prop": "52021PC0206"})),
        (CELEX_BASE + "32024R1689", RawResponse(200, XHTML, OFFICIAL_JOURNAL)),
        (CELEX_BASE + "52021PC0206", RawResponse(300, XHTML, LISTING)),
        (STREAM_BASE + "DOC_1", RawResponse(200, XHTML, PROPOSAL)),
        (STREAM_BASE + "DOC_3", RawResponse(200, XHTML, PROPOSAL_ANNEXES)),
        (hys.feedback_url(14488, 0), as_json(feedback_page(FEEDBACK, last=True))),
        (hys.download_url(ATTACHMENT), RawResponse(200, "application/pdf", PDF)),
    ]


def plenary_record(reference: str) -> dict[str, object]:
    return {
        "src": "https://www.europarl.europa.eu/doceo/document/A-9-2023-0188-AM-001-771_EN.pdf",
        "reference": reference,
        "date": "2023-06-07T00:00:00",
        "seq": "2",
        "id": "A9-0188/2023-2",
        "new": ["Having regard to the opinion of the", "European Central Bank,"],
        "location": ["Citation 4 a (new)"],
        "committee": "IMCO",
    }


def index_entry(com: str = "COM(2021)206", publication: int = 14488) -> hys.IndexEntry:
    return hys.IndexEntry(
        initiative_id=12527,
        short_title="Requirements for Artificial Intelligence",
        reference="Ares(2020)3896535",
        com_references=(com,),
        publications=(
            hys.Publication(
                publication_id=publication,
                type="PROP_REG",
                reference=com,
                com_reference=com,
                total_feedback=len(FEEDBACK),
                published_at=None,
                adopted_at=None,
                feedback_end_at=None,
            ),
        ),
    )


@dataclass
class World:
    root: Path
    inputs: CollectInputs
    fetcher: CachedFetcher
    scripted: ScriptedFetcher

    def collect(
        self,
        query: str = AI_ACT,
        *,
        attachments: bool = True,
        refresh: bool = False,
        code_revision: str = "src-test",
    ) -> CollectResult:
        settings = CollectSettings(
            data_root=self.root,
            code_revision=code_revision,
            attachments=attachments,
            refresh=refresh,
            hardware="test",
        )
        return collect.collect_law(
            query, inputs=self.inputs, settings=settings, fetcher=self.fetcher, clock=lambda: NOW
        )

    def store(self, procedure: str = AI_ACT) -> StageStore:
        slug = procedure.replace("/", "-").replace("(", "-").rstrip(")")
        return StageStore(self.root / "laws" / slug)


def make_world(
    tmp_path: Path,
    script: Script | None = None,
    *,
    index: tuple[hys.IndexEntry, ...] | None = (index_entry(),),
    register: str | None = None,
) -> World:
    dumps = tmp_path / "raw" / "parltrack"
    dumps.mkdir(parents=True)
    write_dump(
        dumps / "ep_dossiers.json.zst",
        [
            ai_act_dossier(),
            dossier("2022/0047(COD)", title="Data Act"),
            dossier("2023/0001(COD)", title="Data Act"),
            dossier(ONGOING, title="Toy Safety", stage_reached="Awaiting committee decision"),
        ],
    )
    write_dump(
        dumps / "ep_amendments.json.zst",
        [
            committee_record(),
            committee_record(id="PE1-1", reference=ONGOING, meps=[]),
            committee_record(id="PE9-9", reference=NEWER_THAN_DUMP, meps=[]),
            # Another law's recent amendment: the dump reaches past the AI Act's end.
            committee_record(id="PE8-8", reference=LATER, meps=[], date=RECENT),
        ],
    )
    write_dump(
        dumps / "ep_plenary_amendments.json.zst",
        [plenary_record(AI_ACT), {**plenary_record(LATER), "date": RECENT}],
    )
    write_dump(
        dumps / "ep_meps.json.zst", [mep_record(197721), mep_record(125042, "Margrete AUKEN")]
    )
    registry = tmp_path / "raw" / "registry"
    registry.mkdir(parents=True)
    (registry / "register.xml").write_text(
        register
        if register is not None
        else export(representative(EQUINET, "Equinet"), representative("111111111111-11", "Other")),
        encoding="utf-8",
    )
    inputs = CollectInputs.under(tmp_path)
    if index is not None:
        hys.write_index(inputs.hys_index, index)
    scripted = ScriptedFetcher(ai_act_script() if script is None else script)
    fetcher = CachedFetcher(
        cache=HttpCache(tmp_path / "cache"),
        fetcher=scripted,
        limiter=RateLimiter(monotonic=lambda: 0.0, sleep=lambda _: None),
        clock=lambda: NOW,
    )
    return World(tmp_path, inputs, fetcher, scripted)


def statuses(law: LawRecord) -> dict[Layer, tuple[LayerStatus, int | None]]:
    return {item.layer: (item.status, item.count) for item in law.coverage}


def row(law: LawRecord, layer: Layer) -> LayerCoverage:
    (found,) = (item for item in law.coverage if item.layer == layer)
    return found


# --- The whole path -------------------------------------------------------------------------


def test_a_procedure_number_becomes_a_complete_bundle_with_typed_coverage(tmp_path: Path) -> None:
    world = make_world(tmp_path)

    result = world.collect()

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
    assert [item.layer for item in law.coverage] == list(collect.LAYERS)
    found = statuses(law)
    assert found["metadata"] == ("complete", 1)
    assert found["proposal"][0] == "complete"
    assert (found["proposal"][1] or 0) > 0
    assert found["final_act"][0] == "complete"
    assert (found["final_act"][1] or 0) > 0
    assert found["parliament_position"] == ("not_collected", None)
    assert found["committee_amendments"] == ("complete", 1)
    assert found["plenary_amendments"] == ("complete", 1)
    assert found["asks"] == ("complete", 3)
    assert found["meetings"] == found["votes"] == ("not_collected", None)
    assert row(law, "meetings").reason == collect.NOT_BUILT_GAP
    # Two MEPs, the register entry, the unresolved company and the citizens aggregate.
    assert found["actors"] == ("complete", 5)


def test_every_record_validates_and_every_passage_quotes_its_document(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    result = world.collect()
    store = world.store()
    receipts = {receipt.stage: receipt for receipt in result.manifest.stages}

    texts = store.read_output(receipts["asks"], "document_texts.jsonl", DocumentText)
    text_of = {text.document_id: text.text for text in texts}
    passages = store.read_output(receipts["asks"], "passages.jsonl", Passage)
    assert passages
    assert all(span_matches(p.span, text_of[p.span.record_id]) for p in passages)
    actors_of = {p.document_id: p.actor_id for p in passages}
    assert actors_of["doc:hys_feedback:1"] == f"actor:tr:{EQUINET}"
    assert actors_of[f"doc:hys_attachment:{ATTACHMENT}"] == f"actor:tr:{EQUINET}"
    assert actors_of["doc:hys_feedback:3"] == CITIZENS_ACTOR_ID
    assert "six months" in text_of[f"doc:hys_attachment:{ATTACHMENT}"]

    documents = store.read_output(receipts["asks"], "documents.jsonl", SourceDocument)
    # Retrieval is dated by the cache, not by the clock of the run.
    assert {d.retrieved_at for d in documents} == {NOW}
    assert {d.url for d in documents if d.source_kind == "hys_feedback"} == {
        hys.feedback_url(14488, 0)
    }

    articles = store.read_output(receipts["texts"], "articles.jsonl", ArticleVersion)
    assert {a.stage for a in articles} == {"proposal", "final_act"}
    amendments = store.read_output(receipts["amendments"], "amendments.jsonl", Amendment)
    assert {a.procedure_id for a in amendments} == {AI_ACT}
    (law,) = store.read_output(receipts["law"], "laws.jsonl", LawRecord)
    assert law == result.law
    actors = store.read_output(receipts["law"], "actors.jsonl", Actor)
    assert {a.kind for a in actors} == {"mep", "organisation", "citizens"}


def test_the_manifest_is_published_last_and_names_every_stage(tmp_path: Path) -> None:
    world = make_world(tmp_path)

    result = world.collect()

    manifest = RunManifest.model_validate_json(result.manifest_path.read_bytes())
    assert manifest == result.manifest == world.store().current()
    assert manifest.status == "complete"
    assert [stage.stage for stage in manifest.stages] == ["texts", "amendments", "asks", "law"]
    assert all(stage.status == "complete" for stage in manifest.stages)
    assert (manifest.run_id, manifest.query, manifest.code_revision) == (
        "20261003T120000Z",
        AI_ACT,
        "src-test",
    )
    assert manifest.config == {"attachments": "yes", "refresh": "no"}
    assert manifest.coverage == result.law.coverage
    assert (result.bundle / "runs" / "20261003T120000Z.json").is_file()


def test_a_rerun_reuses_every_stage_without_a_request_and_refresh_redoes_them(
    tmp_path: Path,
) -> None:
    world = make_world(tmp_path)
    first = world.collect()
    requests = len(world.scripted.calls)

    second = world.collect()

    assert [s.status for s in second.manifest.stages] == ["reused"] * 4
    assert len(world.scripted.calls) == requests
    assert second.law == first.law
    refreshed = world.collect(refresh=True)
    assert all(s.status == "complete" for s in refreshed.manifest.stages)
    assert len(world.scripted.calls) > requests


def test_a_code_change_redoes_the_stages_its_revision_keys(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    world.collect()

    changed = world.collect(code_revision="src-other")

    assert all(s.status == "complete" for s in changed.manifest.stages)


def test_skipping_attachments_is_a_labelled_partial_layer(tmp_path: Path) -> None:
    world = make_world(tmp_path)

    law = world.collect(attachments=False).law

    assert row(law, "asks") == LayerCoverage(
        layer="asks", status="partial", count=3, reason="1 attachment(s) skipped by request"
    )
    assert not any("download" in call for call in world.scripted.calls)


# --- Resolving what was typed ---------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "Artificial Intelligence Act",
        "AI Act",
        "aia",
        "the AI-Act",
        "Reglement sur l'IA",
        "32024R1689",
        "COM(2021) 206",
        "2021/106 (cod)",
    ],
)
def test_a_title_celex_or_com_number_resolves_from_the_catalog(tmp_path: Path, query: str) -> None:
    world = make_world(tmp_path)
    catalog = collect.load_catalog(world.inputs.dossiers, tmp_path / "catalog")

    resolved = collect.resolve_law(query, catalog, world.fetcher)

    assert resolved.procedure_id == AI_ACT
    assert resolved.entry is not None
    assert world.scripted.calls == []


def test_a_number_the_catalog_lacks_is_asked_of_cellar(tmp_path: Path) -> None:
    world = make_world(
        tmp_path,
        [
            ('STR(?c) = "32019L0790"', sparql({"ref": "2016/0280/COD"})),
            ('STR(?c) = "52099PC0001"', sparql({"ref": "2099/0001/COD"})),
        ],
    )
    catalog = collect.load_catalog(world.inputs.dossiers, tmp_path / "catalog")

    by_celex = collect.resolve_law("32019L0790", catalog, world.fetcher)
    by_com = collect.resolve_law("COM(2099)1", catalog, world.fetcher)

    assert (by_celex.procedure_id, by_celex.entry) == ("2016/0280(COD)", None)
    assert (by_com.procedure_id, by_com.entry) == ("2099/0001(COD)", None)


def test_unclear_or_unknown_queries_stop_with_the_reason(tmp_path: Path) -> None:
    world = make_world(
        tmp_path,
        [
            ('STR(?c) = "32019L0790"', sparql({"ref": "2016/0280/COD"}, {"ref": "2016/0281/COD"})),
            ('STR(?c) = "39999R9999"', sparql()),
        ],
    )
    catalog = collect.load_catalog(world.inputs.dossiers, tmp_path / "catalog")

    with pytest.raises(AmbiguousLawError) as title_race:
        collect.resolve_law("Data", catalog, world.fetcher)
    assert title_race.value.choices == (
        ("2022/0047(COD)", "Data Act"),
        ("2023/0001(COD)", "Data Act"),
    )
    with pytest.raises(AmbiguousLawError) as celex_race:
        collect.resolve_law("32019L0790", catalog, world.fetcher)
    assert celex_race.value.choices == (
        ("2016/0280(COD)", "2016/0280(COD)"),
        ("2016/0281(COD)", "2016/0281(COD)"),
    )
    with pytest.raises(CollectError, match="No procedure is known for 39999R9999"):
        collect.resolve_law("39999R9999", catalog, world.fetcher)
    with pytest.raises(CollectError, match="No procedure title"):
        collect.resolve_law("Fishing quotas for the moon", catalog, world.fetcher)
    with pytest.raises(CollectError, match="empty"):
        collect.resolve_law("   ", catalog, world.fetcher)
    with pytest.raises(CollectError, match="CELLAR could not resolve 39999L0001"):
        collect.resolve_law("39999L0001", catalog, world.fetcher)


def test_names_that_disagree_return_the_choices_instead_of_a_guess(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    catalog = collect.load_catalog(world.inputs.dossiers, tmp_path / "catalog")
    one_name_two_laws = {"AI Act": AI_ACT, "AI-Act": ONGOING}

    with pytest.raises(AmbiguousLawError) as two_aliases:
        collect.resolve_law("the AI act", catalog, world.fetcher, one_name_two_laws)
    # "Data Act" is listed for 2022/0047(COD), and 2023/0001(COD) is titled exactly that.
    with pytest.raises(AmbiguousLawError) as alias_and_title:
        collect.resolve_law("the Data Act", catalog, world.fetcher)

    assert two_aliases.value.choices == (
        (AI_ACT, "Artificial Intelligence Act"),
        (ONGOING, "Toy Safety"),
    )
    assert alias_and_title.value.choices == (
        ("2022/0047(COD)", "Data Act"),
        ("2023/0001(COD)", "Data Act"),
    )


def test_a_common_name_whose_procedure_the_dump_lacks_stops_before_any_request(
    tmp_path: Path,
) -> None:
    world = make_world(tmp_path)

    with pytest.raises(
        CollectError,
        match=r"'DSA' is the common name of 2020/0361\(COD\), which the Parltrack dossiers "
        r"dump does not hold: .* type 2020/0361\(COD\) to collect",
    ):
        world.collect("DSA")

    assert world.scripted.calls == []
    assert world.store("2020/0361(COD)").current() is None


def test_the_resolved_law_is_reported_before_any_stage_runs(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    heard: list[tuple[str, int]] = []

    collect.collect_law(
        "AI Act",
        inputs=world.inputs,
        settings=CollectSettings(data_root=tmp_path, code_revision="src-test"),
        fetcher=world.fetcher,
        clock=lambda: NOW,
        on_resolved=lambda law: heard.append((law.procedure_id, len(world.scripted.calls))),
    )

    assert heard == [(AI_ACT, 0)]
    assert world.scripted.calls


def test_a_com_reference_maps_to_its_proposal_celex() -> None:
    assert collect.proposal_celex("COM(2021)206") == "52021PC0206"
    assert collect.proposal_celex("COM(2021)206 final") is None


@given(
    year=st.integers(min_value=1958, max_value=2099),
    number=st.integers(min_value=1, max_value=9999),
)
def test_every_com_number_has_a_proposal_celex_in_the_cellar_shape(year: int, number: int) -> None:
    assert collect.proposal_celex(f"COM({year}){number}") == f"5{year}PC{number:04d}"


# --- Gaps that become labels ----------------------------------------------------------------


def test_a_procedure_newer_than_the_dump_still_collects_what_exists(tmp_path: Path) -> None:
    world = make_world(tmp_path, [("procedure/2025_59>", sparql({"prop": "52025PC0101"}))])

    law = world.collect(NEWER_THAN_DUMP).law

    assert (law.title, law.status, law.com_reference) == (
        NEWER_THAN_DUMP,
        "unknown",
        "COM(2025)101",
    )
    found = statuses(law)
    assert found["metadata"] == ("missing", None)
    assert found["proposal"] == ("not_collected", None)
    assert found["final_act"] == ("missing", None)
    assert found["committee_amendments"] == ("complete", 1)
    assert found["plenary_amendments"] == ("missing", 0)
    assert row(law, "asks").reason == "No feedback on the initiatives carrying COM(2025)101"


def test_an_ongoing_procedure_has_no_final_act_yet_and_partial_amendments(tmp_path: Path) -> None:
    world = make_world(tmp_path, [("procedure/2024_100>", sparql())])

    law = world.collect(ONGOING).law

    found = statuses(law)
    assert found["final_act"] == ("not_applicable", None)
    assert found["proposal"] == ("missing", None)
    assert found["committee_amendments"] == ("partial", 1)
    assert row(law, "asks").reason == (
        "No COM reference is known, and Have Your Say is joined by COM reference only"
    )


def test_an_unreachable_cellar_leaves_labelled_gaps_and_the_catalog_com_number(
    tmp_path: Path,
) -> None:
    script = [item for item in ai_act_script() if item[0] != "procedure/2021_106>"]
    world = make_world(tmp_path, script)

    result = world.collect()

    assert statuses(result.law)["proposal"] == statuses(result.law)["final_act"]
    assert row(result.law, "final_act").status == "not_collected"
    assert (row(result.law, "final_act").reason or "").startswith("CELLAR did not answer")
    assert result.law.com_reference == "COM(2021)206"
    assert result.law.celex_final == "32024R1689"
    assert row(result.law, "asks").status == "complete"
    assert result.manifest.stages[0].status == "partial"


@pytest.mark.parametrize(
    ("final_act", "status"),
    [
        (RawResponse(404, XHTML, b""), "missing"),
        (RawResponse(500, XHTML, b""), "not_collected"),
        (RawResponse(200, XHTML, b"<html><body><p>No articles here</p></body></html>"), "partial"),
        (RawResponse(200, XHTML, b"\xff\xfe not utf-8"), "not_collected"),
    ],
)
def test_each_way_an_act_can_fail_has_its_own_status(
    tmp_path: Path, final_act: RawResponse, status: LayerStatus
) -> None:
    script = [
        (CELEX_BASE + "32024R1689", final_act) if fragment == CELEX_BASE + "32024R1689" else item
        for item in ai_act_script()
        for fragment in (item[0],)
    ]
    world = make_world(tmp_path, script)

    final = row(world.collect().law, "final_act")

    assert final.status == status
    assert (final.reason or "").startswith("32024R1689: ")


def test_the_proposals_annexes_are_collected_as_annex_provisions(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    result = world.collect()
    receipts = {receipt.stage: receipt for receipt in result.manifest.stages}
    articles = world.store().read_output(receipts["texts"], "articles.jsonl", ArticleVersion)
    assert [a.provision for a in articles if a.stage == "proposal" and a.kind == "annex"] == [
        "Annex I",
        "Annex III",
    ]


@pytest.mark.parametrize(
    ("annex", "reason"),
    [
        (None, "52021PC0206: " + STREAM_BASE + "DOC_3: No response: unscripted"),
        (
            RawResponse(200, XHTML, b"<html><body><p>Cover page only</p></body></html>"),
            "52021PC0206 annex stream 1: An annex stream with no 'ANNEX' heading line",
        ),
    ],
)
def test_a_lost_or_unsplit_annex_leaves_the_proposal_partial_and_says_which(
    tmp_path: Path, annex: RawResponse | None, reason: str
) -> None:
    script = [item for item in ai_act_script() if item[0] != STREAM_BASE + "DOC_3"]
    if annex is not None:
        script.append((STREAM_BASE + "DOC_3", annex))
    world = make_world(tmp_path, script)

    proposal = row(world.collect().law, "proposal")

    assert proposal.status == "partial"
    assert (proposal.count or 0) > 0
    assert (proposal.reason or "").startswith(reason)


def test_several_final_acts_are_listed_and_none_is_fetched(tmp_path: Path) -> None:
    script = ai_act_script()
    script[0] = (
        "procedure/2021_106>",
        sparql({"final": "32024R1689", "prop": "52021PC0206"}, {"final": "32024R1690"}),
    )
    world = make_world(tmp_path, script)

    final = row(world.collect().law, "final_act")

    assert final.status == "not_collected"
    assert final.reason == "CELLAR lists several: 32024R1689, 32024R1690; none is chosen"
    assert not any(call.endswith("32024R1689") for call in world.scripted.calls)


def test_consultation_gaps_are_counted_by_kind(tmp_path: Path) -> None:
    script = [item for item in ai_act_script() if "download" not in item[0]]
    second = index_entry(publication=25429)
    world = make_world(tmp_path, script, index=(index_entry(), second))

    asks = row(world.collect().law, "asks")

    assert asks == LayerCoverage(
        layer="asks",
        status="partial",
        count=3,
        reason="1 publication(s) not read: the request failed; 1 attachment(s) not downloaded",
    )


def test_an_unreadable_attachment_is_counted_and_kept_as_a_document(tmp_path: Path) -> None:
    script = [
        (fragment, RawResponse(200, "application/pdf", b"%PDF-1.7 broken"))
        if "download" in fragment
        else (fragment, response)
        for fragment, response in ai_act_script()
    ]
    world = make_world(tmp_path, script)

    result = world.collect()

    asks = row(result.law, "asks")
    assert (asks.status, asks.reason) == (
        "partial",
        "1 attachment(s) with no extractable text (invalid_pdf 1)",
    )
    receipt = result.manifest.stages[2]
    documents = world.store().read_output(receipt, "documents.jsonl", SourceDocument)
    (attached,) = (d for d in documents if d.source_kind == "hys_attachment")
    assert attached.extraction_status == "failed"


def test_lost_ligature_glyphs_are_restored_before_passages_and_noted(tmp_path: Path) -> None:
    # pypdf returns U+0000 for a ligature glyph its font leaves unmapped (rev-obw8).
    lost = make_pdf(("We ask that signi\x00cant changes are noti\x00ed in \x00 days.",))
    script = [
        (fragment, RawResponse(200, "application/pdf", lost))
        if "download" in fragment
        else (fragment, response)
        for fragment, response in ai_act_script()
    ]
    world = make_world(tmp_path, script)

    result = world.collect()

    asks = row(result.law, "asks")
    assert (asks.status, asks.reason) == (
        "complete",
        "1 attachment(s) had PDF ligature glyphs with no character, restored by a word "
        "guess or replaced by a space (see extraction_method)",
    )
    receipt = result.manifest.stages[2]
    documents = world.store().read_output(receipt, "documents.jsonl", SourceDocument)
    (attached,) = (d for d in documents if d.source_kind == "hys_attachment")
    assert attached.extraction_method == "pypdf+glyph_repair:guessed=2,unresolved=1"
    texts = world.store().read_output(receipt, "document_texts.jsonl", DocumentText)
    (text,) = (t for t in texts if t.document_id == attached.document_id)
    assert text.text == "We ask that significant changes are notified in   days."
    passages = world.store().read_output(receipt, "passages.jsonl", Passage)
    quoted = [p for p in passages if p.document_id == attached.document_id]
    assert quoted
    assert all(span_matches(p.span, text.text) for p in quoted)
    quotes = [text.text[p.span.start : p.span.end] for p in quoted]
    assert any("significant" in quote for quote in quotes)


def test_without_the_index_a_title_search_finds_the_initiative_and_says_so(
    tmp_path: Path,
) -> None:
    search = hys.search_url(page=0, size=hys.TITLE_SEARCH_SIZE, text="Artificial Intelligence Act")
    proposal_publication: dict[str, object] = {
        "id": 14488,
        "type": "PROP_REG",
        "reference": "COM(2021)206",
        "totalFeedback": 3,
    }
    script = [
        (urllib.parse.unquote_plus(search), as_json(search_page([12527], last=True, total=1))),
        (hys.initiative_url(12527), as_json(initiative(12527, [proposal_publication]))),
        *ai_act_script(),
    ]
    world = make_world(tmp_path, script, index=None)

    asks = row(world.collect().law, "asks")

    assert (asks.status, asks.count) == ("complete", 3)
    assert asks.reason == "Initiative found by title search: the Have Your Say index is not built"


def test_a_failed_title_search_is_a_labelled_layer_not_collected(tmp_path: Path) -> None:
    world = make_world(tmp_path, index=None)

    result = world.collect()

    # The search failed, so the run did not get the feedback: not evidence of none.
    asks = row(result.law, "asks")
    assert asks.status == "not_collected"
    assert (asks.reason or "").startswith("Have Your Say title search failed")
    receipt = next(stage for stage in result.manifest.stages if stage.stage == "asks")
    assert receipt.status == "partial"
    assert receipt.errors == (asks.reason,)


def test_a_law_with_nothing_to_analyse_stops_without_a_manifest(tmp_path: Path) -> None:
    world = make_world(tmp_path, [("procedure/2022_47>", sparql())])

    with pytest.raises(CollectError, match="no amendments and no consultation submissions"):
        world.collect("2022/0047(COD)")

    assert world.store("2022/0047(COD)").current() is None


# --- Reruns after a failure, and stale inputs -----------------------------------------------


def stage_statuses(result: CollectResult) -> list[tuple[str, str]]:
    return [(stage.stage, stage.status) for stage in result.manifest.stages]


def test_a_stage_left_partial_by_an_outage_is_rebuilt_when_the_source_returns(
    tmp_path: Path,
) -> None:
    feedback_page_url = hys.feedback_url(14488, 0)
    script = [item for item in ai_act_script() if item[0] != feedback_page_url]
    world = make_world(tmp_path, script)

    down = world.collect()

    # The feedback request failed: not evidence that nobody answered the consultation.
    asks = row(down.law, "asks")
    assert (asks.status, asks.count) == ("not_collected", 0)
    assert asks.reason == "1 publication(s) not read: the request failed"
    assert ("asks", "partial") in stage_statuses(down)

    world.scripted.script[:] = ai_act_script()
    back = world.collect()

    assert stage_statuses(back) == [
        ("texts", "reused"),
        ("amendments", "reused"),
        ("asks", "complete"),
        ("law", "complete"),
    ]
    assert row(back.law, "asks").status == "complete"
    law_receipt = back.manifest.stages[3]
    (stored,) = world.store().read_output(law_receipt, "laws.jsonl", LawRecord)
    assert stored == back.law
    assert sum(feedback_page_url in call for call in world.scripted.calls) == 2


def test_an_unanswered_cellar_with_several_com_numbers_is_not_collected_until_it_answers(
    tmp_path: Path,
) -> None:
    script = [item for item in ai_act_script() if item[0] != "procedure/2021_106>"]
    world = make_world(tmp_path, script)
    dossier_record = ai_act_dossier()
    amended = {
        "date": "2023-01-10T00:00:00",
        "type": "Amended legislative proposal for reconsultation published",
        "docs": [{"title": "COM(2023)0010"}],
    }
    events = cast("list[object]", dossier_record["events"])
    write_dump(world.inputs.dossiers, [{**dossier_record, "events": [*events, amended]}])

    down = world.collect()

    asks = row(down.law, "asks")
    assert asks.status == "not_collected"
    assert (asks.reason or "").startswith(
        "No COM reference was resolved, so Have Your Say was not searched: CELLAR did not answer"
    )
    assert ("asks", "partial") in stage_statuses(down)

    world.scripted.script[:] = ai_act_script()
    back = world.collect()

    # The amendments were complete, so they are reused; the gaps CELLAR caused are not.
    assert [status for _, status in stage_statuses(back)] == [
        "complete",
        "reused",
        "complete",
        "complete",
    ]
    assert row(back.law, "proposal").status == "complete"
    assert row(back.law, "asks").status == "complete"


def test_a_refreshed_dossiers_dump_that_changed_the_law_rebuilds_its_record(
    tmp_path: Path,
) -> None:
    world = make_world(tmp_path, [("procedure/2024_100>", sparql())])
    first = world.collect(ONGOING)
    assert first.law.status == "ongoing"
    completed = dossier(ONGOING, title="Toy Safety", stage_reached="Procedure completed")
    write_dump(world.inputs.dossiers, [ai_act_dossier(), completed])

    second = world.collect(ONGOING)

    # The stages whose records carry the catalog entry are rebuilt; asks never read it.
    assert stage_statuses(second) == [
        ("texts", "complete"),
        ("amendments", "complete"),
        ("asks", "reused"),
        ("law", "complete"),
    ]
    (stored,) = world.store(ONGOING).read_output(second.manifest.stages[3], "laws.jsonl", LawRecord)
    assert (stored.status, stored.stage_reached) == ("completed", "Procedure completed")


def test_each_amendment_names_its_authors_groups_on_the_day_it_was_tabled(
    tmp_path: Path,
) -> None:
    world = make_world(tmp_path)
    # 197721 sat with Renew until July 2024, then the EPP; the amendment is from 2022.
    # No spell covers the 2019-2024 term, so her group on the tabling day is unknown.
    auken = {
        **mep_record(125042, "Margrete AUKEN"),
        "Groups": [
            {"groupid": "S&D", "start": "2024-07-16T00:00:00", "end": "9999-12-31T00:00:00"}
        ],
    }
    write_dump(world.inputs.meps, [switcher(197721), auken])

    result = world.collect()

    receipt = result.manifest.stages[1]
    amendments = world.store().read_output(receipt, "amendments.jsonl", Amendment)
    committee = next(item for item in amendments if item.stage == "committee")
    assert committee.author_ids == ("actor:mep:197721", "actor:mep:125042")
    # 125042's spells leave 2019 to 2024 uncovered: unknown, not the latest group.
    assert committee.author_groups == ("Renew", None)
    actors = world.store().read_output(receipt, "actors.jsonl", Actor)
    assert {a.actor_id: a.political_group for a in actors}["actor:mep:197721"] == "EPP"


def test_amendments_from_a_dump_that_ends_before_the_law_did_are_partial(
    tmp_path: Path,
) -> None:
    world = make_world(tmp_path)
    write_dump(world.inputs.committee_amendments, [committee_record()])
    write_dump(world.inputs.plenary_amendments, [{**plenary_record(AI_ACT), "date": None}])

    law = world.collect().law

    committee = row(law, "committee_amendments")
    assert (committee.status, committee.count) == ("partial", 1)
    assert committee.reason == (
        "The Parltrack committee amendments dump ends on 2022-01-25, before the procedure's "
        "last activity on 2024-07-12: later amendments may be absent"
    )
    plenary = row(law, "plenary_amendments")
    assert plenary.status == "partial"
    assert (plenary.reason or "").startswith(
        "The Parltrack plenary amendments dump ends on an unknown date"
    )


def test_a_dumps_reach_is_scanned_once_and_cached_by_its_hash(tmp_path: Path) -> None:
    dated = write_dump(tmp_path / "dated.json.zst", [committee_record()])
    undated = write_dump(tmp_path / "undated.json.zst", [{"id": 1}])
    catalog = tmp_path / "catalog"

    assert collect.dump_reach(dated, "a" * 64, catalog) == date(2022, 1, 25)
    assert collect.dump_reach(undated, "b" * 64, catalog) is None
    dated.unlink()
    undated.unlink()
    # Read back from the cache: the dumps are gone.
    assert collect.dump_reach(dated, "a" * 64, catalog) == date(2022, 1, 25)
    assert collect.dump_reach(undated, "b" * 64, catalog) is None
    with pytest.raises(CollectError, match="unreadable"):
        collect.dump_reach(dated, "c" * 64, catalog)


def test_a_package_publication_of_another_law_is_skipped_and_counted(tmp_path: Path) -> None:
    base = index_entry()
    other = base.publications[0].model_copy(
        update={"publication_id": 999, "reference": "COM(2021)207", "com_reference": None}
    )
    shared = base.publications[0].model_copy(update={"reference": "COM(2021)0206 and COM(2021)207"})
    entry = base.model_copy(update={"publications": (shared, other)})
    world = make_world(tmp_path, index=(entry,))

    asks = row(world.collect().law, "asks")

    assert (asks.status, asks.count) == ("complete", 3)
    assert asks.reason == "1 publication(s) of another law of the package skipped"
    assert not any("999" in call for call in world.scripted.calls)


def test_refresh_asks_have_your_say_again(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    world.collect()
    page = hys.feedback_url(14488, 0)
    download = hys.download_url(ATTACHMENT)
    asked = [sum(url in call for call in world.scripted.calls) for url in (page, download)]

    world.collect(refresh=True)

    again = [sum(url in call for call in world.scripted.calls) for url in (page, download)]
    assert again == [count + 1 for count in asked]


def test_an_index_crawl_failure_is_named_and_an_empty_answer_is_not_collected(
    tmp_path: Path,
) -> None:
    world = make_world(tmp_path)
    failures = tuple(
        hys.IndexFailure(initiative_id=number, error="HTTP 500") for number in range(1, 7)
    )
    hys.write_failures(hys.failures_path(world.inputs.hys_index), failures[:1])

    found = row(world.collect().law, "asks")

    assert (found.status, found.count) == ("complete", 3)
    assert found.reason == (
        "The Have Your Say index lacks 1 initiative(s) its crawl could not read (1); "
        "run setup again to retry them"
    )

    other = make_world(tmp_path / "other", index=(index_entry(com="COM(2099)1"),))
    hys.write_failures(hys.failures_path(other.inputs.hys_index), failures)

    lacking = row(other.collect().law, "asks")

    assert lacking.status == "not_collected"
    assert lacking.reason == (
        "The Have Your Say index lacks 6 initiative(s) its crawl could not read "
        "(1, 2, 3, 4, 5, ...); run setup again to retry them"
    )


def test_a_publication_the_api_does_not_serve_is_a_source_gap(tmp_path: Path) -> None:
    unserved = RawResponse(200, "text/plain", b"bad_request")
    script = [
        (fragment, unserved) if fragment == hys.feedback_url(14488, 0) else (fragment, response)
        for fragment, response in ai_act_script()
    ]
    world = make_world(tmp_path, script)

    result = world.collect()

    asks = row(result.law, "asks")
    assert (asks.status, asks.reason) == ("missing", "1 publication(s) not served by the API")
    assert ("asks", "complete") in stage_statuses(result)


# --- Inputs that stop the run ---------------------------------------------------------------


def test_missing_required_files_stop_the_run_before_any_request(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    world.inputs.register.unlink()
    world.inputs.meps.unlink()

    with pytest.raises(CollectError, match=r"ep_meps\.json\.zst, .*register\.xml"):
        world.collect()

    assert world.scripted.calls == []


@pytest.mark.parametrize("damaged", ["dossiers", "committee_amendments", "meps", "hys_index"])
def test_a_corrupt_input_is_an_explicit_error(tmp_path: Path, damaged: str) -> None:
    world = make_world(tmp_path)
    path: Path = getattr(world.inputs, damaged)
    path.write_bytes(b"not what it claims to be")

    with pytest.raises(CollectError):
        world.collect()


def test_a_dump_under_another_name_is_refused(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    renamed = world.inputs.meps.with_name("meps.json")
    world.inputs.meps.rename(renamed)
    world.inputs = replace(world.inputs, meps=renamed)

    with pytest.raises(CollectError, match="not a Parltrack dump name"):
        world.collect()


def test_an_empty_register_export_is_an_explicit_error(tmp_path: Path) -> None:
    world = make_world(tmp_path, register=export())

    with pytest.raises(CollectError, match="register export is unreadable"):
        world.collect()


# --- Small helpers --------------------------------------------------------------------------


def test_the_source_revision_follows_every_python_file(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    before = collect.source_revision(tmp_path / "pkg")
    assert before == collect.source_revision(tmp_path / "pkg")
    assert before.startswith("src-")
    assert len(before) == len("src-") + 12
    (tmp_path / "pkg" / "a.py").write_text("x = 2\n")
    assert collect.source_revision(tmp_path / "pkg") != before


def test_retrieval_falls_back_to_the_run_clock_when_nothing_is_cached(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    assert collect.fetched_at(world.fetcher, "https://example.org/nothing", NOW) == NOW


# --- The command ----------------------------------------------------------------------------


def scripted_cli(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    monkeypatch.setattr(cli, "UrllibFetcher", lambda: world.scripted)


def test_the_command_prints_the_coverage_table_and_the_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world = make_world(tmp_path)
    scripted_cli(monkeypatch, world)

    logging.getLogger("pypdf").setLevel(logging.NOTSET)
    status = cli.main(["collect", "2021/0106(COD)", "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    lines = output.splitlines()
    assert status == 0
    assert logging.getLogger("pypdf").level == logging.ERROR
    assert lines[1].startswith("Collected 2021/0106(COD) Artificial Intelligence Act in ")
    rows = {line.split()[0]: line.split(maxsplit=2)[1:] for line in lines[2:13]}
    assert rows["committee_amendments"] == ["complete", "1"]
    assert rows["meetings"] == ["not_collected", collect.NOT_BUILT_GAP]
    assert f"manifest: {world.store().root / 'manifest.json'}" in output


@pytest.mark.parametrize(
    ("query", "script", "procedure", "found"),
    [
        (
            ["the", "AI-Act"],
            None,
            AI_ACT,
            "titled 'Artificial Intelligence Act' in the Parltrack dossiers dump",
        ),
        (
            [NEWER_THAN_DUMP],
            [("procedure/2025_59>", sparql({"prop": "52025PC0101"}))],
            NEWER_THAN_DUMP,
            "which the Parltrack dossiers dump does not hold",
        ),
    ],
)
def test_the_command_names_the_law_it_resolved_before_collecting_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    query: list[str],
    script: Script | None,
    procedure: str,
    found: str,
) -> None:
    world = make_world(tmp_path, script)
    scripted_cli(monkeypatch, world)

    status = cli.main(["collect", *query, "--data-root", str(tmp_path)])

    first, collected = capsys.readouterr().out.splitlines()[:2]
    manifest = world.store(procedure).current()
    assert status == 0
    assert first == f"Resolved {' '.join(query)!r} to {procedure}, {found}"
    assert collected.startswith(f"Collected {procedure} ")
    assert manifest is not None
    assert manifest.query == " ".join(query)


def test_the_command_lists_the_choices_for_an_unclear_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world = make_world(tmp_path)
    scripted_cli(monkeypatch, world)

    status = cli.main(["collect", "Data", "Act", "--data-root", str(tmp_path)])

    assert status == 1
    error = capsys.readouterr().err
    assert "'Data Act' names more than one procedure" in error
    assert "  2022/0047(COD)  Data Act" in error


def test_the_command_reports_a_stop_and_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world = make_world(tmp_path)
    world.inputs.register.unlink()
    scripted_cli(monkeypatch, world)
    monkeypatch.setenv("INFLUENCE_DATA_ROOT", str(tmp_path))

    status = cli.main(["collect", "AI Act", "--no-attachments", "--refresh"])

    assert status == 1
    assert "Required input files are missing" in capsys.readouterr().err


def test_the_command_needs_a_query(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["collect"])
    assert stopped.value.code == 2
    assert "query" in capsys.readouterr().err


def test_records_written_by_a_run_round_trip_from_disk(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    result = world.collect()
    receipt = result.manifest.stages[1]
    (output,) = (o for o in receipt.outputs if o.path.endswith("amendments.jsonl"))

    amendments = list(read_records(world.store().output_path(output), Amendment))

    assert len(amendments) == output.records == 2
