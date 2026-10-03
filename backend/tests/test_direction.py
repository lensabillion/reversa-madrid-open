"""Part 7, TOWARDS: the direction of each amendment, and its counts by group, Member and actor.

The table is real-looking legal edits, one or more per rule, including the traps: "shall"
to "may" is weaker, an inserted "not" that makes "shall not apply" is an exemption, and
Parltrack's "deleted" marker is a deletion.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_collect import make_world, scripted_cli
from test_parltrack import committee_record, mep_record, write_dump
from test_pipeline import collected, matching_world

from influence import cli
from influence.extraction.records import StageStore
from influence.schemas.atlas import Actor, Amendment, Direction, LawRecord, span_matches
from influence.schemas.atlas_view import AtlasView
from influence.schemas.directions import DirectionCounts, DirectionsView
from influence.services import direction, pipeline
from influence.services.pipeline import PipelineError
from influence.services.tabling_groups import LATEST_SPELL_FALLBACK, TABLING_DAY_GROUPS

AI_ACT = "2021/0106(COD)"
SLUG = "2021-0106-COD"
LATER = datetime(2026, 10, 3, 18, 0, tzinfo=UTC)
LOGS = "Providers shall keep the logs."

# (old, new, direction, side the quote is in, quote); a None quote means nothing to quote.
CASES: list[tuple[str | None, str, Direction, str | None, str | None]] = [
    # delete
    (LOGS, "deleted", "delete", "old_text", LOGS),
    (LOGS, " Deleted ", "delete", "old_text", LOGS),
    (LOGS, "", "delete", "old_text", LOGS),
    (None, "deleted", "delete", "new_text", "deleted"),
    (
        "Providers shall keep the logs and report them to the authority every year.",
        "Providers shall keep the logs.",
        "delete",
        "old_text",
        "and report them to the authority every year",
    ),
    # unknown
    (None, LOGS, "unknown", None, None),
    ("word " * 900, LOGS, "unknown", None, None),
    # keep
    (LOGS, "Providers  shall keep the\nlogs.", "keep", None, None),
    # exempt: the inserted "not" completes "shall not apply"; it is not a stricter "shall".
    (
        "This Regulation shall apply to providers.",
        "This Regulation shall not apply to providers.",
        "exempt",
        "new_text",
        "shall not apply",
    ),
    (
        LOGS,
        "Providers shall keep the logs, except micro-enterprises.",
        "exempt",
        "new_text",
        "except",
    ),
    (
        "Member States shall ensure compliance.",
        "By way of derogation, Member States may exempt SMEs.",
        "exempt",
        "new_text",
        "derogation",
    ),
    # delay
    (
        "This Regulation shall apply from 2 August 2025.",
        "This Regulation shall apply from 2 August 2027.",
        "delay",
        "new_text",
        "2027",
    ),
    (
        "Providers shall report within six months.",
        "Providers shall report within 24 months.",
        "delay",
        "new_text",
        "24 months",
    ),
    # A postponement outranks the "may" it brings.
    (
        "The Commission shall review this Regulation.",
        "The Commission shall review this Regulation and may postpone its application.",
        "delay",
        "new_text",
        "postpone",
    ),
    # stricter
    ("Providers may keep the logs.", LOGS, "stricter", "new_text", "shall"),
    (
        "Providers may use the data.",
        "Providers are prohibited from using the data.",
        "stricter",
        "new_text",
        "prohibited",
    ),
    (
        "Providers may share the data.",
        "Providers may not share the data.",
        "stricter",
        "new_text",
        "may not",
    ),
    (
        LOGS,
        "Providers shall keep the logs for at least six months.",
        "stricter",
        "new_text",
        "at least",
    ),
    # Removing an exemption tightens the rule; the quote is in the original.
    (
        "Providers shall keep logs, except SMEs.",
        "Providers shall keep logs.",
        "stricter",
        "old_text",
        "except",
    ),
    ("", "Providers must keep the logs.", "stricter", "new_text", "must"),
    # weaker: the trap the narrow part 4 rule also gets right.
    (LOGS, "Providers may keep the logs.", "weaker", "new_text", "may"),
    (LOGS, "Providers keep the logs where feasible.", "weaker", "old_text", "shall"),
    # add
    (
        "",
        "This Regulation concerns the logs.",
        "add",
        "new_text",
        "This Regulation concerns the logs.",
    ),
    # A new deadline where none was replaced is not a delay.
    (
        LOGS,
        "Providers shall keep the logs within six months.",
        "add",
        "new_text",
        "within six months",
    ),
    # other
    (
        "This Regulation shall apply from 2 August 2027.",
        "This Regulation shall apply from 2 August 2025.",
        "other",
        "new_text",
        "2025",
    ),
    # One stricter cue swapped for another: the tie falls through.
    ("Providers shall keep logs.", "Providers must keep logs.", "other", "new_text", "must"),
    ("Providers shall promptly keep the logs.", LOGS, "other", "old_text", "promptly"),
]


@pytest.mark.parametrize(("old", "new", "expected", "field", "quote"), CASES)
def test_each_rule_labels_its_edit_and_quotes_the_wording_that_decided_it(
    old: str | None, new: str, expected: Direction, field: str | None, quote: str | None
) -> None:
    reading = direction.read_change(old, new)

    assert reading.direction == expected
    assert direction.change_direction(old, new) == expected
    if quote is None:
        assert reading.evidence is None
        return
    assert reading.evidence is not None
    side, start, end = reading.evidence
    assert side == field
    assert (new if side == "new_text" else old or "")[start:end] == quote


def test_an_unknown_reading_says_why() -> None:
    assert direction.read_change(None, LOGS).unknown_reason == "original_unknown"
    assert direction.read_change("word " * 900, LOGS).unknown_reason == "over_long"
    assert direction.read_change(LOGS, "Providers may keep the logs.").unknown_reason is None


def test_the_precedence_lists_every_direction_once() -> None:
    assert sorted(direction.PRECEDENCE) == sorted(get_args(Direction.__value__))


# --- Properties -----------------------------------------------------------------------------

_WORDS = st.sampled_from(
    [
        "shall",
        "may",
        "not",
        "apply",
        "except",
        "at",
        "least",
        "2025",
        "2027",
        "six",
        "24",
        "months",
        "postpone",
        "providers",
        "logs",
        "deleted",
        ",",
        ".",
    ]
)
_TEXT = st.lists(_WORDS, max_size=15).map(" ".join)


@given(old=st.none() | _TEXT, new=_TEXT)
def test_the_classifier_is_total_deterministic_and_quotes_exactly(
    old: str | None, new: str
) -> None:
    reading = direction.read_change(old, new)

    assert reading.direction in get_args(Direction.__value__)
    assert direction.read_change(old, new) == reading
    if reading.evidence is not None:
        side, start, end = reading.evidence
        source = new if side == "new_text" else old or ""
        assert 0 <= start < end <= len(source)
        assert source[start:end].strip() == source[start:end]


@given(text=_TEXT)
def test_an_unchanged_text_is_never_stricter_or_weaker(text: str) -> None:
    assert direction.change_direction(text, text) in {"keep", "delete"}


# --- Aggregation ----------------------------------------------------------------------------


def amendment(
    name: str,
    old: str | None,
    new: str,
    *,
    authors: tuple[int, ...] = (),
    stage: str = "committee",
) -> Amendment:
    return Amendment.model_validate(
        {
            "amendment_id": f"am:{SLUG}:ENVI:{name}",
            "procedure_id": AI_ACT,
            "document_id": "doc:parltrack:ep_amendments",
            "stage": stage,
            "author_ids": [f"actor:mep:{author}" for author in authors],
            "tabled_on": date(2022, 3, 1),
            "old_text": old,
            "new_text": new,
        }
    )


def mep(mep_id: int, group: str | None) -> Actor:
    return Actor(
        actor_id=f"actor:mep:{mep_id}",
        kind="mep",
        name=f"Member {mep_id}",
        mep_id=mep_id,
        political_group=group,
        resolution="mep_id",
    )


MEPS = (mep(1, "PPE"), mep(2, "S&D"), mep(3, "PPE"), mep(4, None))


def law() -> LawRecord:
    return LawRecord(
        procedure_id=AI_ACT, title="Artificial Intelligence Act", status="completed", coverage=()
    )


def test_counts_by_stage_group_and_member_with_one_quoted_example_per_direction() -> None:
    amendments = [
        amendment("PE1-1", LOGS, "Providers may keep the logs.", authors=(1,)),
        # Co-signed across groups: once in PPE, once in S&D, once for each Member.
        amendment("PE1-2", "Providers may keep the logs.", LOGS, authors=(1, 2, 1)),
        amendment("PE1-3", LOGS, "deleted", authors=(4,), stage="plenary"),
        amendment("PE1-4", None, LOGS, authors=(99,), stage="plenary"),
        amendment("PE1-5", "word " * 900, LOGS, authors=(3,)),
        amendment("PE1-6", LOGS, "Providers may keep the logs, or not.", authors=(3,)),
    ]

    view = direction.build_directions(
        law(), "run-1", reversed(amendments), MEPS, None, generated_at=LATER
    )

    assert view.amendments == 6
    assert view.counts == DirectionCounts(stricter=1, weaker=2, delete=1, unknown=2)
    assert (view.unknown_reasons.over_long, view.unknown_reasons.original_unknown) == (1, 1)
    assert [(row.stage, row.amendments) for row in view.by_stage] == [
        ("committee", 4),
        ("plenary", 2),
    ]
    assert [(row.group, row.amendments, row.counts) for row in view.by_group] == [
        ("PPE", 4, DirectionCounts(stricter=1, weaker=2, unknown=1)),
        ("S&D", 1, DirectionCounts(stricter=1)),
    ]
    assert view.without_group == 2
    assert [(m.actor_id, m.name, m.political_group, m.amendments) for m in view.top_members] == [
        ("actor:mep:1", "Member 1", "PPE", 2),
        ("actor:mep:3", "Member 3", "PPE", 2),
        ("actor:mep:2", "Member 2", "S&D", 1),
        ("actor:mep:4", "Member 4", None, 1),
        ("actor:mep:99", "actor:mep:99", None, 1),
    ]
    sources = {item.amendment_id: item for item in amendments}
    assert [(e.direction, e.amendment_id[-5:], e.span.text) for e in view.examples] == [
        ("delete", "PE1-3", LOGS),
        ("stricter", "PE1-2", "shall"),
        ("weaker", "PE1-1", "may"),
    ]
    for example in view.examples:
        source = sources[example.amendment_id]
        text = source.new_text if example.span.field == "new_text" else source.old_text or ""
        assert span_matches(example.span, text)
    assert (view.actors_status, view.atlas_run_id, view.actors) == ("no_atlas_view", None, ())
    assert view.actors_reason is not None
    assert (view.method, view.limitations) == (
        direction.METHOD,
        (*direction.LIMITATIONS, TABLING_DAY_GROUPS, LATEST_SPELL_FALLBACK),
    )


def test_the_top_members_are_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(direction, "TOP_MEMBERS", 1)
    amendments = [amendment("PE1-1", LOGS, "deleted", authors=(1, 2))]

    view = direction.build_directions(law(), "run-1", amendments, MEPS, None, generated_at=LATER)

    assert [member.actor_id for member in view.top_members] == ["actor:mep:1"]


def published_view(tmp_path: Path) -> AtlasView:
    return pipeline.build_view(
        collected(matching_world(tmp_path)), generated_at=LATER, publish_prose=True
    )


def test_actor_directions_come_only_from_published_links(tmp_path: Path) -> None:
    atlas = published_view(tmp_path)
    (link,) = [link for link in atlas.bundle.links if link.status == "published"]
    ask = next(ask for ask in atlas.bundle.asks if ask.ask_id == link.ask_id)
    # A second, unconfirmed link from another actor is never counted.
    unconfirmed = link.model_copy(
        update={"link_id": "link:other", "status": "unconfirmed", "ask_id": "ask:other"}
    )
    atlas = atlas.model_copy(
        update={
            "bundle": atlas.bundle.model_copy(update={"links": (*atlas.bundle.links, unconfirmed)})
        }
    )

    view = direction.build_directions(law(), atlas.run_id, [], (), atlas, generated_at=LATER)

    assert (view.actors_status, view.actors_reason, view.atlas_run_id) == (
        "from_published_links",
        None,
        atlas.run_id,
    )
    (row,) = view.actors
    assert (row.actor_id, row.published_links, row.link_ids) == (
        ask.actor_id,
        1,
        (link.link_id,),
    )
    assert row.name == "Acme Unknown Lobby"
    # The linked amendment inserts "for at least six months after ...".
    assert row.counts == DirectionCounts(stricter=1)


def test_a_joint_ask_counts_once_for_each_actor_and_an_unnamed_actor_keeps_its_id(
    tmp_path: Path,
) -> None:
    atlas = published_view(tmp_path)
    (link,) = [link for link in atlas.bundle.links if link.status == "published"]
    asks = tuple(
        ask.model_copy(
            update={
                "joint_actor_ids": (
                    "actor:name:hys.partner",
                    ask.actor_id,
                    "actor:name:hys.partner",
                )
            }
        )
        if ask.ask_id == link.ask_id
        else ask
        for ask in atlas.bundle.asks
    )
    atlas = atlas.model_copy(update={"bundle": atlas.bundle.model_copy(update={"asks": asks})})

    view = direction.build_directions(law(), atlas.run_id, [], (), atlas, generated_at=LATER)

    lead = next(ask.actor_id for ask in asks if ask.ask_id == link.ask_id)
    # Ties on links are ordered by actor ID.
    assert sorted([(row.actor_id, row.name, row.published_links) for row in view.actors]) == sorted(
        [
            (lead, "Acme Unknown Lobby", 1),
            ("actor:name:hys.partner", "actor:name:hys.partner", 1),
        ]
    )
    assert [row.actor_id for row in view.actors] == sorted([lead, "actor:name:hys.partner"])


def test_a_view_without_published_links_gives_no_actor_directions(tmp_path: Path) -> None:
    atlas = published_view(tmp_path)
    links = tuple(link.model_copy(update={"status": "unconfirmed"}) for link in atlas.bundle.links)
    atlas = atlas.model_copy(update={"bundle": atlas.bundle.model_copy(update={"links": links})})

    view = direction.build_directions(law(), atlas.run_id, [], (), atlas, generated_at=LATER)

    assert (view.actors_status, view.actors) == ("no_published_links", ())
    assert view.actors_reason is not None
    assert f"publishes none of its {len(links)} shown links" in view.actors_reason


def test_a_published_link_to_a_record_the_view_lacks_is_an_error(tmp_path: Path) -> None:
    atlas = published_view(tmp_path)
    atlas = atlas.model_copy(update={"bundle": atlas.bundle.model_copy(update={"asks": ()})})

    with pytest.raises(PipelineError, match="its bundle lacks"):
        direction.build_directions(law(), atlas.run_id, [], (), atlas, generated_at=LATER)


def test_a_view_of_another_run_is_used_only_while_its_amendments_are_unchanged(
    tmp_path: Path,
) -> None:
    """Regression: a view of an older run once mixed its links with newer amendments."""
    atlas = published_view(tmp_path)
    same = atlas.bundle.amendments

    fresh = direction.build_directions(law(), "run-new", same, (), atlas, generated_at=LATER)
    changed = tuple(a.model_copy(update={"new_text": "Something else."}) for a in same)
    stale = direction.build_directions(law(), "run-new", changed, (), atlas, generated_at=LATER)

    assert fresh.actors_status == "from_published_links"
    assert (stale.actors_status, stale.actors, stale.atlas_run_id) == (
        "stale_atlas_view",
        (),
        atlas.run_id,
    )
    assert stale.actors_reason is not None
    assert "run-new" in stale.actors_reason
    assert "have changed since" in stale.actors_reason


def test_the_view_round_trips_through_its_file(tmp_path: Path) -> None:
    view = direction.build_directions(
        law(), "run-1", [amendment("PE1-1", LOGS, "deleted")], MEPS, None, generated_at=LATER
    )

    path = direction.write_directions(view, tmp_path)

    assert path == tmp_path / direction.VIEW_FILE
    assert DirectionsView.model_validate_json(path.read_bytes()) == view
    assert (view.procedure_id, view.slug, view.run_id) == (AI_ACT, SLUG, "run-1")


# --- The command ----------------------------------------------------------------------------


def directions_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`test_collect`'s world with one weaker edit by a PPE Member and one deletion."""
    world = make_world(tmp_path)
    write_dump(
        world.inputs.committee_amendments,
        [
            committee_record(
                id="PE7-1", seq=1, old=[LOGS], new=["Providers may keep the logs."], meps=[1]
            ),
            committee_record(id="PE7-2", seq=2, old=[LOGS], new=["deleted"], meps=[2]),
        ],
    )
    conservative = {
        **mep_record(1, "Axel EXAMPLE"),
        "Groups": [{"groupid": "PPE", "start": "2019-07-02T00:00:00", "end": "9999-12-31"}],
    }
    benifei = {
        **mep_record(2, "Brando BENIFEI"),
        # The S&D spell covering the tabling day, which the shared record leaves out.
        "Groups": [
            {"groupid": "S&D", "start": "2019-07-02T00:00:00", "end": "2024-07-15T00:00:00"}
        ],
    }
    write_dump(world.inputs.meps, [conservative, benifei])
    scripted_cli(monkeypatch, world)


def test_the_command_collects_counts_and_writes_the_directions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directions_world(tmp_path, monkeypatch)

    status = cli.main(["directions", AI_ACT, "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    path = tmp_path / "laws" / SLUG / direction.VIEW_FILE
    assert status == 0
    assert "\nCollected 2021/0106(COD) Artificial Intelligence Act in " in output
    assert (
        # The world's one plenary amendment has no original wording.
        "Directions of 3 amendments: weaker 1, delete 1, unknown 1\n"
        "  committee: weaker 1, delete 1\n"
        "  plenary: unknown 1\n"
        "  PPE (1): weaker 1\n"
        "  S&D (1): delete 1\n"
        "Actors: no_atlas_view: No atlas view exists for this law; run `influence atlas` "
        "first. Actor directions are read only through published links.\n"
        f'  delete   am:{SLUG}:ENVI:PE7-2  "{LOGS}"\n'
        f'  weaker   am:{SLUG}:ENVI:PE7-1  "may"\n'
        f"directions: {path}\n"
    ) in output
    view = DirectionsView.model_validate_json(path.read_bytes())
    assert view.run_id == StageStore(path.parent).current().run_id  # pyright: ignore[reportOptionalMemberAccess]


def test_the_command_reads_the_atlas_view_and_says_when_it_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted_cli(monkeypatch, matching_world(tmp_path))
    assert cli.main(["atlas", AI_ACT, "--data-root", str(tmp_path)]) == 0
    capsys.readouterr()

    status = cli.main(["directions", AI_ACT, "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    assert status == 0
    assert "Actors: no_published_links: The atlas view of run " in output
    view = DirectionsView.model_validate_json(
        (tmp_path / "laws" / SLUG / direction.VIEW_FILE).read_bytes()
    )
    assert view.atlas_run_id is not None


def test_the_command_prints_the_actors_of_published_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted_cli(monkeypatch, matching_world(tmp_path))
    real = pipeline.build_view

    def publishing(collected: pipeline.Collected, *, generated_at: datetime) -> AtlasView:
        return real(collected, generated_at=generated_at, publish_prose=True)

    monkeypatch.setattr(cli, "build_view", publishing)
    assert cli.main(["atlas", AI_ACT, "--data-root", str(tmp_path)]) == 0
    capsys.readouterr()

    status = cli.main(["directions", AI_ACT, "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    assert status == 0
    assert "Actors:" not in output
    assert "  Acme Unknown Lobby (1 published links): stricter 1\n" in output


def test_the_command_keeps_the_bundle_when_the_directions_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directions_world(tmp_path, monkeypatch)

    def broken(_view: DirectionsView, bundle: Path) -> Path:
        raise OSError(f"cannot write in {bundle.name}")

    monkeypatch.setattr(cli, "write_directions", broken)

    status = cli.main(["directions", AI_ACT, "--data-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert status == 1
    assert "Directions of" not in captured.out
    assert captured.err == (
        f"error: cannot write in {SLUG}\n"
        "The collected bundle is kept; no directions file was written.\n"
    )
    assert not (tmp_path / "laws" / SLUG / direction.VIEW_FILE).exists()
