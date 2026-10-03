"""Part 1 · Collect on a tiny public record: every layer, every gap, every way to stop.

The world below is written in the real formats (Parltrack dump lines, the register export,
Have Your Say JSON, CELLAR XHTML) using the connector tests' own builders, and answered by
a scripted fetcher: no test reaches the network.
"""

import logging
import urllib.parse
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_cellar import (
    CELEX_BASE,
    LISTING,
    OFFICIAL_JOURNAL,
    PROPOSAL,
    STREAM_BASE,
    XHTML,
    ScriptedFetcher,
    sparql,
)
from test_hys import as_json, feedback, feedback_page, initiative, make_pdf, search_page
from test_parltrack import ai_act_dossier, committee_record, dossier, mep_record, write_dump
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
from influence.services.law_query import com_reference_from_celex

AI_ACT = "2021/0106(COD)"
ONGOING = "2024/0100(COD)"
NEWER_THAN_DUMP = "2025/0059(COD)"
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
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
        ],
    )
    write_dump(dumps / "ep_plenary_amendments.json.zst", [plenary_record(AI_ACT)])
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
        collect.resolve_law("Data Act", catalog, world.fetcher)
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


def test_a_com_reference_maps_to_its_proposal_celex() -> None:
    assert collect.proposal_celex("COM(2021)206") == "52021PC0206"
    assert collect.proposal_celex("COM(2021)206 final") is None


@given(
    year=st.integers(min_value=1958, max_value=2099),
    number=st.integers(min_value=1, max_value=9999),
)
def test_every_com_number_round_trips_through_its_proposal_celex(year: int, number: int) -> None:
    celex = collect.proposal_celex(f"COM({year}){number}")
    assert celex is not None
    assert com_reference_from_celex(celex) == f"COM({year}){number}"


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
        reason="1 publication(s) not served or not read; 1 attachment(s) not downloaded",
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
    assert (asks.status, asks.reason) == ("partial", "1 attachment(s) with no extractable text")
    receipt = result.manifest.stages[2]
    documents = world.store().read_output(receipt, "documents.jsonl", SourceDocument)
    (attached,) = (d for d in documents if d.source_kind == "hys_attachment")
    assert attached.extraction_status == "failed"


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


def test_a_failed_title_search_is_a_labelled_missing_layer(tmp_path: Path) -> None:
    world = make_world(tmp_path, index=None)

    asks = row(world.collect().law, "asks")

    assert asks.status == "missing"
    assert (asks.reason or "").startswith("Have Your Say title search failed")


def test_a_law_with_nothing_to_analyse_stops_without_a_manifest(tmp_path: Path) -> None:
    world = make_world(tmp_path, [("procedure/2022_47>", sparql())])

    with pytest.raises(CollectError, match="no amendments and no consultation submissions"):
        world.collect("2022/0047(COD)")

    assert world.store("2022/0047(COD)").current() is None


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
    assert status == 0
    assert logging.getLogger("pypdf").level == logging.ERROR
    assert output.startswith("Collected 2021/0106(COD) Artificial Intelligence Act in ")
    rows = {line.split()[0]: line.split(maxsplit=2)[1:] for line in output.splitlines()[1:12]}
    assert rows["committee_amendments"] == ["complete", "1"]
    assert rows["meetings"] == ["not_collected", collect.NOT_BUILT_GAP]
    assert f"manifest: {world.store().root / 'manifest.json'}" in output


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
