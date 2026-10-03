"""Part 7's HOW: the channels one law was lobbied through, counted from collected records."""

import urllib.parse
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_collect import EQUINET, ai_act_script, make_world, scripted_cli
from test_coordinated import AI_ACT, DRAFT, LATER, MEPS, SLUG, amendment, coordinated_world, mep
from test_hys import as_json, initiative, search_page

from influence import cli
from influence.extraction.records import StageStore
from influence.repositories import hys
from influence.schemas.atlas import (
    Actor,
    ActorAlias,
    LawRecord,
    LayerCoverage,
    Passage,
    SourceDocument,
    SourceSpan,
)
from influence.schemas.channels import ChannelsView, KeyCount, SubmitterGroup
from influence.services import channels, collect
from influence.services.pipeline import PipelineError

SHA = "0" * 64
PROPOSED = date(2021, 4, 21)


def feedback_document(
    number: int,
    *,
    publication: int | None = 14488,
    published: date | None = date(2021, 6, 1),
    kind: str = "hys_feedback",
) -> SourceDocument:
    url = (
        hys.feedback_url(publication, 0)
        if publication is not None
        else "https://example.org/feedback"
    )
    return SourceDocument.model_validate(
        {
            "document_id": f"doc:{kind}:{number}",
            "procedure_id": AI_ACT,
            "source_kind": kind,
            "url": url,
            "published_at": None
            if published is None
            else datetime(published.year, published.month, published.day, 9, tzinfo=UTC),
            "retrieved_at": LATER,
            "sha256": SHA,
            "extraction_status": "extracted",
        }
    )


def passage(document: SourceDocument, actor_id: str) -> Passage:
    return Passage(
        passage_id=f"passage:{document.document_id}:0",
        procedure_id=AI_ACT,
        document_id=document.document_id,
        actor_id=actor_id,
        span=SourceSpan(record_id=document.document_id, start=0, end=4, text="text"),
        submitted_at=document.published_at,
    )


def organisation(
    name: str,
    *,
    register_id: str | None = None,
    category: str | None = None,
    documents: tuple[str, ...] = (),
) -> Actor:
    return Actor(
        actor_id=f"actor:tr:{register_id}" if register_id else f"actor:name:hys.{name}",
        kind="organisation",
        name=name,
        register_id=register_id,
        category=category,
        aliases=tuple(
            ActorAlias(name=name, source_kind="hys_feedback", document_id=document)
            for document in documents
        ),
        resolution="register_id" if register_id else "unresolved",
    )


CITIZENS = Actor(
    actor_id="actor:citizens:aggregate", kind="citizens", name="Citizens", resolution="unresolved"
)


def law(
    *, proposed: date | None = PROPOSED, completed: date | None = date(2024, 5, 21)
) -> LawRecord:
    return LawRecord(
        procedure_id=AI_ACT,
        title="Artificial Intelligence Act",
        status="completed",
        proposed_on=proposed,
        completed_on=completed,
        coverage=(
            LayerCoverage(layer="metadata", status="complete", count=1),
            LayerCoverage(layer="meetings", status="not_collected", reason="Not built"),
            LayerCoverage(layer="votes", status="not_collected", reason="Not built"),
        ),
    )


# --- Dates ----------------------------------------------------------------------------------


def test_dates_split_around_the_reference_day_which_counts_as_after() -> None:
    split = channels.split_dates([date(2021, 4, 20), PROPOSED, date(2021, 5, 1), None], PROPOSED)

    assert split.model_dump() == {
        "reference_date": PROPOSED,
        "total": 4,
        "before": 1,
        "on_or_after": 2,
        "undated": 1,
        "unplaced": 0,
    }


def test_dated_records_are_unplaced_when_the_reference_is_unknown() -> None:
    split = channels.split_dates([date(2021, 4, 20), None], None)

    assert (split.before, split.on_or_after, split.undated, split.unplaced) == (0, 0, 1, 1)


@given(
    dates=st.lists(st.one_of(st.none(), st.dates())),
    reference=st.one_of(st.none(), st.dates()),
)
def test_every_record_is_placed_exactly_once(
    dates: list[date | None], reference: date | None
) -> None:
    split = channels.split_dates(dates, reference)

    assert split.before + split.on_or_after + split.undated + split.unplaced == split.total
    assert split.total == len(dates)
    assert split.undated == dates.count(None)


# --- Consultation ---------------------------------------------------------------------------


def test_feedback_is_counted_by_publication_stage_and_by_who_sent_it() -> None:
    one = feedback_document(1, published=date(2020, 7, 1), publication=8000)
    two = feedback_document(2)
    three = feedback_document(3, published=None)
    four = feedback_document(4, published=date(2021, 8, 1))
    silent = feedback_document(5, publication=None)
    attachment = feedback_document(6, kind="hys_attachment")
    lobby = organisation("Lobby", register_id=EQUINET, category="Trade associations")
    unnamed = organisation("Unregistered", documents=(four.document_id, "doc:hys_feedback:99"))
    passages = [
        passage(one, lobby.actor_id),
        passage(two, lobby.actor_id),
        passage(attachment, lobby.actor_id),
        passage(three, CITIZENS.actor_id),
        passage(silent, "actor:name:hys.absent"),
    ]

    view = channels.consultation_channel(
        [attachment, silent, four, three, two, one],
        passages,
        [lobby, unnamed, CITIZENS],
        {14488: "PROP_REG"},
    )

    assert (view.feedback, view.attachments, view.feedback_without_submitter) == (5, 1, 0)
    assert [
        (item.publication_id, item.publication_type, item.feedback, item.earliest, item.latest)
        for item in view.by_publication
    ] == [
        (8000, None, 1, date(2020, 7, 1), date(2020, 7, 1)),
        (14488, "PROP_REG", 3, date(2021, 6, 1), date(2021, 8, 1)),
        (None, None, 1, date(2021, 6, 1), date(2021, 6, 1)),
    ]
    assert (
        view.publication_type_gap == "The Have Your Say index states no type for publication 8000"
    )
    assert view.submitters == 4
    assert view.by_actor_kind == (
        SubmitterGroup(key="organisation", feedback=3, submitters=2),
        SubmitterGroup(key="citizens", feedback=1, submitters=1),
        SubmitterGroup(key="unknown", feedback=1, submitters=1),
    )
    assert view.by_register_category == (
        SubmitterGroup(key="unknown", feedback=3, submitters=3),
        SubmitterGroup(key="Trade associations", feedback=2, submitters=1),
    )
    assert (view.organisations_with_register_id, view.organisations) == (1, 2)


def test_feedback_no_record_names_a_submitter_for_is_counted_as_such() -> None:
    view = channels.consultation_channel([feedback_document(1)], [], [], {14488: "PROP_REG"})

    assert (view.feedback, view.submitters, view.feedback_without_submitter) == (1, 0, 1)
    assert view.publication_type_gap is None
    assert view.by_actor_kind == ()


def test_publication_types_are_unknown_without_the_index() -> None:
    view = channels.consultation_channel([feedback_document(1)], [], [], None)
    empty = channels.consultation_channel([], [], [], None)

    assert view.by_publication[0].publication_type is None
    assert view.publication_type_gap == channels.INDEX_GAP
    assert (empty.by_publication, empty.publication_type_gap) == ((), None)


def test_publication_types_come_from_the_index_where_it_states_one() -> None:
    entry = hys.IndexEntry(
        initiative_id=1,
        short_title=None,
        reference=None,
        com_references=(),
        publications=tuple(
            hys.Publication(
                publication_id=publication,
                type=kind,
                reference=None,
                com_reference=None,
                total_feedback=None,
                published_at=None,
                adopted_at=None,
                feedback_end_at=None,
            )
            for publication, kind in ((1, "ROADMAP"), (2, None))
        ),
    )

    assert channels.publication_types([entry]) == {1: "ROADMAP"}


# --- Members --------------------------------------------------------------------------------


def test_amendments_are_counted_by_stage_committee_group_and_tabling_member() -> None:
    plenary = amendment("PE9-1", authors=()).model_copy(
        update={"stage": "plenary", "committee": None}
    )
    absent = amendment("PE4-1", authors=(77,)).model_copy(
        update={"author_names": ("Outside DUMP",)}
    )
    unnamed = amendment("PE4-2", authors=(78, 79)).model_copy(update={"author_names": ("",)})
    amendments = [
        amendment("PE1-1", authors=(1, 2)),
        amendment("PE1-2", authors=(1,), committee="ITRE"),
        amendment("PE1-3", authors=(4,)),
        plenary,
        absent,
        unnamed,
    ]

    view = channels.mep_channel(amendments, MEPS)

    assert view.amendments == 6
    assert view.by_stage == (KeyCount(key="committee", count=5), KeyCount(key="plenary", count=1))
    assert view.by_committee == (
        KeyCount(key="ENVI", count=4),
        KeyCount(key="ITRE", count=1),
        KeyCount(key="unknown", count=1),
    )
    assert view.by_political_group == (
        KeyCount(key="PPE", count=2),
        KeyCount(key="S&D", count=1),
    )
    assert (view.with_known_group, view.group_unknown, view.no_known_author) == (2, 3, 1)
    assert view.tabling_meps == 6
    assert [(m.actor_id, m.name, m.political_group, m.amendments) for m in view.top_meps] == [
        ("actor:mep:1", "Member 1", "PPE", 2),
        ("actor:mep:2", "Member 2", "S&D", 1),
        ("actor:mep:4", "Member 4", None, 1),
        ("actor:mep:77", "Outside DUMP", None, 1),
        ("actor:mep:78", "actor:mep:78", None, 1),
        ("actor:mep:79", "actor:mep:79", None, 1),
    ]


def test_only_the_top_members_are_listed() -> None:
    amendments = [amendment(f"PE1-{n}", authors=(n,)) for n in range(1, channels.TOP_MEPS + 6)]

    view = channels.mep_channel(amendments, [])

    assert view.tabling_meps == channels.TOP_MEPS + 5
    assert len(view.top_meps) == channels.TOP_MEPS


@given(
    authors=st.lists(
        st.lists(st.integers(min_value=1, max_value=6), max_size=4, unique=True), max_size=15
    )
)
def test_group_counts_cover_every_amendment_with_a_known_group(authors: list[list[int]]) -> None:
    amendments = [amendment(f"PE1-{n}", authors=tuple(names)) for n, names in enumerate(authors)]
    meps = (*MEPS, mep(5, "RE"))

    view = channels.mep_channel(amendments, meps)

    assert sum(item.count for item in view.by_political_group) >= view.with_known_group
    assert view.with_known_group + view.group_unknown + view.no_known_author == view.amendments
    assert sum(item.count for item in view.by_stage) == view.amendments
    assert sum(item.count for item in view.by_committee) == view.amendments


# --- Coalitions -----------------------------------------------------------------------------


def test_coalitions_count_open_cosigning_and_coordinated_wording_across_groups() -> None:
    amendments = [
        amendment("PE1-1", authors=(1, 2), inserted="short words"),
        amendment("PE1-2", authors=(1, 3), inserted="other short words"),
        amendment("PE2-1", authors=(1,)),
        amendment("PE2-2", authors=(2,), committee="ITRE"),
    ]

    view = channels.coalition_channel(amendments, MEPS)

    assert (view.amendments, view.cosigned, view.cosigned_across_groups) == (4, 2, 1)
    assert (view.coordinated_clusters, view.cross_group_clusters) == (1, 1)
    assert view.amendments_in_cross_group_clusters == 2
    assert view.coordinated.compared == 2


# --- The view and the command ---------------------------------------------------------------


def test_the_view_records_its_method_and_round_trips_through_its_file(tmp_path: Path) -> None:
    document = feedback_document(1, published=date(2020, 1, 1))
    view = channels.build_channels(
        law(proposed=None),
        "run-1",
        documents=[document, feedback_document(2, published=None)],
        passages=[passage(document, CITIZENS.actor_id)],
        actors=[CITIZENS, *MEPS],
        amendments=[amendment("PE1-1", authors=(1,)), amendment("PE1-2", DRAFT, tabled=None)],
        types=None,
        generated_at=LATER,
    )
    path = channels.write_channels(view, tmp_path)

    assert (view.procedure_id, view.slug, view.run_id, view.method) == (
        AI_ACT,
        SLUG,
        "run-1",
        channels.METHOD,
    )
    assert view.limitations == channels.LIMITATIONS
    assert [row.layer for row in view.votes_and_meetings] == ["meetings", "votes"]
    assert (
        view.timing.feedback_vs_proposal.unplaced,
        view.timing.feedback_vs_proposal.undated,
    ) == (
        1,
        1,
    )
    assert view.timing.amendments_vs_completion.model_dump() == {
        "reference_date": date(2024, 5, 21),
        "total": 2,
        "before": 1,
        "on_or_after": 0,
        "undated": 1,
        "unplaced": 0,
    }
    assert path == tmp_path / channels.VIEW_FILE
    assert ChannelsView.model_validate_json(path.read_bytes()) == view


def test_the_command_collects_counts_the_channels_and_writes_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    coordinated_world(tmp_path, monkeypatch)

    status = cli.main(["channels", AI_ACT, "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    path = tmp_path / "laws" / SLUG / channels.VIEW_FILE
    assert status == 0
    assert "\nCollected 2021/0106(COD) Artificial Intelligence Act in " in output
    assert (
        "Consultation: 3 feedback from 3 submitters on 1 publication(s); "
        "1 of 2 organisations carry a register ID\n"
        "  publication 14488 (PROP_REG): 3 feedback\n"
        "Timing: of 3 feedback, 0 before the proposal, 3 on or after, 0 undated, "
        "0 with no proposal date to place them\n"
        "Members: 4 amendments by 4 Members (1 with no known author); by group: PPE 1, S&D 1\n"
        "Coalitions: 0 of 4 amendments co-signed across groups; 1 coordinated clusters "
        "across groups hold 2 amendments\n"
        f"Meetings: not_collected ({collect.NOT_BUILT_GAP})\n"
        f"Votes: not_collected ({collect.NOT_BUILT_GAP})\n"
        f"channels: {path}\n"
    ) in output
    view = ChannelsView.model_validate_json(path.read_bytes())
    assert view.run_id == StageStore(path.parent).current().run_id  # pyright: ignore[reportOptionalMemberAccess]


def test_the_command_without_the_index_reports_publication_types_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    search = hys.search_url(page=0, size=hys.TITLE_SEARCH_SIZE, text="Artificial Intelligence Act")
    proposal: dict[str, object] = {"id": 14488, "type": "PROP_REG", "reference": "COM(2021)206"}
    script = [
        (urllib.parse.unquote_plus(search), as_json(search_page([12527], last=True, total=1))),
        (hys.initiative_url(12527), as_json(initiative(12527, [proposal]))),
        *ai_act_script(),
    ]
    world = make_world(tmp_path, script, index=None)
    scripted_cli(monkeypatch, world)

    status = cli.main(["channels", AI_ACT, "--data-root", str(tmp_path)])

    path = tmp_path / "laws" / SLUG / channels.VIEW_FILE
    view = ChannelsView.model_validate_json(path.read_bytes())
    assert status == 0
    assert view.consultation.publication_type_gap == channels.INDEX_GAP
    assert "(type unknown)" in capsys.readouterr().out


def test_the_command_keeps_the_bundle_when_the_channels_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    coordinated_world(tmp_path, monkeypatch)

    def broken(_view: ChannelsView, bundle: Path) -> Path:
        raise PipelineError(f"cannot write in {bundle.name}")

    monkeypatch.setattr(cli, "write_channels", broken)

    status = cli.main(["channels", AI_ACT, "--data-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert status == 1
    assert "Consultation:" not in captured.out
    assert captured.err == (
        f"error: cannot write in {SLUG}\n"
        "The collected bundle is kept; no channels file was written.\n"
    )
    assert not (tmp_path / "laws" / SLUG / channels.VIEW_FILE).exists()
