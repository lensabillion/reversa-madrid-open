"""Coordinated amendments: clusters of near-identical inserted wording across groups.

`DRAFT` stands for the outside draft: 30 distinct words, so it has 26 five-word runs and
the similarity of two variants can be worked out by hand in each test.
"""

import json
import random
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_collect import make_world, scripted_cli
from test_parltrack import committee_record, mep_record, write_dump

from influence import cli
from influence.extraction.records import StageStore
from influence.schemas.atlas import Actor, Amendment, LawRecord, span_matches
from influence.schemas.coordinated import CoordinatedView
from influence.services import coordinated, pipeline
from influence.services.pipeline import PipelineError
from influence.services.tabling_groups import LATEST_SPELL_FALLBACK, TABLING_DAY_GROUPS

AI_ACT = "2021/0106(COD)"
SLUG = "2021-0106-COD"
LATER = datetime(2026, 10, 3, 15, 30, tzinfo=UTC)
WORDS = tuple(f"word{number}" for number in range(30))
DRAFT = " ".join(WORDS)
BASE = "Providers shall keep the logs."


def variant(*, first: int = 0, last: int = 0) -> str:
    """The draft with its first and last words replaced, each costing that many runs."""
    return " ".join(
        (
            *(f"head{n}" for n in range(first)),
            *WORDS[first : 30 - last],
            *(f"tail{n}" for n in range(last)),
        )
    )


def amendment(
    name: str,
    inserted: str = DRAFT,
    *,
    authors: tuple[int, ...] = (),
    old: str | None = BASE,
    tabled: date | None = date(2022, 3, 1),
    committee: str = "ENVI",
) -> Amendment:
    return Amendment(
        amendment_id=f"am:{SLUG}:{committee}:{name}",
        procedure_id=AI_ACT,
        document_id="doc:parltrack:ep_amendments",
        stage="committee",
        committee=committee,
        author_ids=tuple(f"actor:mep:{author}" for author in authors),
        author_names=tuple(f"Member {author}" for author in authors),
        tabled_on=tabled,
        target_provision="Article 12",
        old_text=old,
        new_text=f"{BASE} {inserted}" if inserted else "",
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


# --- Clusters -------------------------------------------------------------------------------


def test_the_same_wording_from_two_groups_is_one_cluster_that_quotes_each_member() -> None:
    later = amendment("PE2-9", authors=(2,), tabled=date(2022, 6, 13), committee="IMCO")
    earlier = amendment("PE1-4", authors=(1,))

    (cluster,), counts = coordinated.find_coordinated([later, earlier], MEPS)

    assert cluster.cluster_id == f"coord:{SLUG}:ENVI:PE1-4"
    assert [member.amendment_id for member in cluster.members] == [
        earlier.amendment_id,
        later.amendment_id,
    ]
    assert (cluster.cross_group, cluster.political_groups) == (True, ("PPE", "S&D"))
    assert (cluster.inserted_words, cluster.min_similarity) == (30, 1.0)
    for member, source in zip(cluster.members, (earlier, later), strict=True):
        assert [span.text for span in member.inserted] == [DRAFT]
        assert all(span.field == "new_text" for span in member.inserted)
        assert all(span_matches(span, source.new_text) for span in member.inserted)
        assert (member.committee, member.tabled_on) == (source.committee, source.tabled_on)
    assert counts.model_dump() == {
        "amendments": 2,
        "compared": 2,
        "too_short": 0,
        "not_comparable": 0,
    }


def test_two_different_edits_to_one_paragraph_are_not_a_cluster() -> None:
    """The paragraph they both amend is shared wording; only what each inserts counts."""
    paragraph = " ".join(f"law{number}" for number in range(60))
    one = amendment("PE1-1", authors=(1,), old=paragraph).model_copy(
        update={"new_text": f"{paragraph} {DRAFT}"}
    )
    other = amendment("PE1-2", authors=(2,), old=paragraph).model_copy(
        update={"new_text": f"{paragraph} {' '.join(f'other{n}' for n in range(30))}"}
    )

    clusters, counts = coordinated.find_coordinated([one, other], MEPS)

    assert clusters == ()
    assert counts.compared == 2


def test_wording_is_joined_at_the_threshold_and_not_below_it() -> None:
    # One word replaced at the end: 25 of 27 distinct runs are shared (0.93).
    near = amendment("PE1-2", variant(last=1), authors=(2,))
    # Three replaced: 23 of 29 (0.79), under the 0.8 threshold.
    far = amendment("PE1-3", variant(last=3), authors=(2,), committee="ITRE")

    (cluster,), _ = coordinated.find_coordinated([amendment("PE1-1", authors=(1,)), near], MEPS)
    apart, _ = coordinated.find_coordinated([amendment("PE1-1", authors=(1,)), far], MEPS)

    assert cluster.min_similarity == pytest.approx(25 / 27)
    assert apart == ()


def test_a_chain_of_similar_pairs_is_one_cluster_that_reports_its_least_similar_pair() -> None:
    # Each end differs from the middle by two words (24 of 28 runs, 0.86); the two ends
    # differ by four (22 of 30, 0.73) and are joined only through the middle.
    ends = (
        amendment("PE1-1", variant(last=2), authors=(1,)),
        amendment("PE1-3", variant(first=2), authors=(2,)),
    )
    middle = amendment("PE1-2", authors=(3,))

    alone, _ = coordinated.find_coordinated(ends, MEPS)
    (cluster,), _ = coordinated.find_coordinated([*ends, middle], MEPS)

    assert alone == ()
    assert len(cluster.members) == 3
    assert cluster.min_similarity == pytest.approx(22 / 30)
    assert cluster.min_similarity < coordinated.SIMILARITY_THRESHOLD
    assert cluster.inserted_words == 30


def test_an_unknown_original_is_read_as_a_new_provision() -> None:
    known = amendment("PE1-1", authors=(1,), old="").model_copy(update={"new_text": DRAFT})
    unknown = amendment("PE1-2", authors=(2,), old=None).model_copy(update={"new_text": DRAFT})

    (cluster,), _ = coordinated.find_coordinated([known, unknown], MEPS)

    assert cluster.cross_group
    assert [span.text for member in cluster.members for span in member.inserted] == [DRAFT] * 2


# --- Across groups --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "second", "reason"),
    [
        ((1,), (1,), "one Member tabling the same text in two committees"),
        ((1, 2), (2,), "a co-signed amendment and a copy by one of its signatories"),
        ((1,), (3,), "two Members of the same group"),
        ((1,), (3, 2), "the groups overlap"),
        ((1,), (4,), "a Member whose group the dump does not state"),
        ((1,), (), "a plenary amendment with no Members listed"),
        ((1,), (99,), "an author absent from the MEP dump"),
    ],
)
def test_a_cluster_spans_groups_only_with_disjoint_authors_of_disjoint_known_groups(
    first: tuple[int, ...], second: tuple[int, ...], reason: str
) -> None:
    pair = [
        amendment("PE1-1", authors=first),
        amendment("PE2-1", authors=second, committee="ITRE"),
    ]

    (cluster,), _ = coordinated.find_coordinated(pair, MEPS)

    assert not cluster.cross_group, reason
    assert len(cluster.members) == 2


def test_clusters_that_span_groups_come_first_then_more_groups_then_more_members() -> None:
    other = " ".join(f"other{number}" for number in range(30))
    third = " ".join(f"third{number}" for number in range(30))
    meps = (*MEPS, mep(5, "RE"))
    amendments = [
        # Same group twice, three members: listed last although it is the largest.
        amendment("PE1-1", other, authors=(1,)),
        amendment("PE1-2", other, authors=(3,)),
        amendment("PE1-3", other, authors=(3,), committee="ITRE"),
        # Two groups.
        amendment("PE2-1", third, authors=(1,)),
        amendment("PE2-2", third, authors=(2,)),
        # Three groups.
        amendment("PE3-1", authors=(1,)),
        amendment("PE3-2", authors=(2,)),
        amendment("PE3-3", authors=(5,)),
    ]

    clusters, _ = coordinated.find_coordinated(amendments, meps)

    assert [(c.cross_group, c.political_groups, len(c.members)) for c in clusters] == [
        (True, ("PPE", "RE", "S&D"), 3),
        (True, ("PPE", "S&D"), 2),
        (False, ("PPE",), 3),
    ]
    assert clusters[0].members[0].amendment_id.endswith("PE3-1")


def test_an_undated_member_is_listed_after_the_dated_ones() -> None:
    undated = amendment("PE0-1", authors=(1,), tabled=None)
    dated = amendment("PE9-9", authors=(2,))

    (cluster,), _ = coordinated.find_coordinated([undated, dated], MEPS)

    assert [member.tabled_on for member in cluster.members] == [date(2022, 3, 1), None]
    assert cluster.cluster_id.endswith("PE9-9")


# --- What is not compared -------------------------------------------------------------------


def test_short_edits_deletions_and_over_long_amendments_are_counted_not_clustered() -> None:
    short = " ".join(WORDS[: coordinated.MIN_INSERTED_WORDS - 1])
    enough = " ".join(WORDS[: coordinated.MIN_INSERTED_WORDS])
    long = amendment("PE5-1", authors=(1,)).model_copy(update={"new_text": "word " * 900})
    amendments = [
        amendment("PE1-1", short, authors=(1,)),
        amendment("PE1-2", short, authors=(2,)),
        amendment("PE2-1", "", authors=(1,)),
        amendment("PE2-2", "", authors=(2,)),
        amendment("PE3-1", enough, authors=(1,)),
        amendment("PE3-2", enough, authors=(2,)),
        long,
        long.model_copy(update={"amendment_id": f"am:{SLUG}:ENVI:PE5-2"}),
    ]

    (cluster,), counts = coordinated.find_coordinated(amendments, MEPS)

    assert {member.amendment_id[-5:] for member in cluster.members} == {"PE3-1", "PE3-2"}
    assert cluster.inserted_words == coordinated.MIN_INSERTED_WORDS
    assert counts.model_dump() == {
        "amendments": 8,
        "compared": 2,
        "too_short": 4,
        "not_comparable": 2,
    }


def test_no_amendments_is_no_clusters() -> None:
    clusters, counts = coordinated.find_coordinated([], [])

    assert clusters == ()
    assert counts.amendments == 0


# --- Properties -----------------------------------------------------------------------------

# A three-word vocabulary makes random amendments share many runs, so clusters, chains and
# near misses all occur.
_INSERTIONS = st.lists(st.sampled_from(["alpha", "beta", "gamma"]), min_size=8, max_size=20)


@given(
    insertions=st.lists(_INSERTIONS, max_size=12),
    authors=st.lists(st.integers(min_value=1, max_value=4), min_size=12, max_size=12),
    shuffler=st.randoms(),
)
def test_clusters_are_disjoint_exactly_quoted_and_independent_of_input_order(
    insertions: list[list[str]], authors: list[int], shuffler: random.Random
) -> None:
    amendments = [
        amendment(f"PE1-{number}", " ".join(words), authors=(authors[number],))
        for number, words in enumerate(insertions)
    ]
    sources = {item.amendment_id: item.new_text for item in amendments}

    clusters, counts = coordinated.find_coordinated(amendments, MEPS)

    members = [member for cluster in clusters for member in cluster.members]
    assert len({member.amendment_id for member in members}) == len(members) <= counts.compared
    assert counts.compared + counts.too_short + counts.not_comparable == counts.amendments
    for cluster in clusters:
        assert cluster.inserted_words >= coordinated.MIN_INSERTED_WORDS
        assert 0 < cluster.min_similarity <= 1
    for member in members:
        assert all(span_matches(span, sources[member.amendment_id]) for span in member.inserted)
    shuffled = amendments.copy()
    shuffler.shuffle(shuffled)
    assert coordinated.find_coordinated(shuffled, MEPS) == (clusters, counts)


# --- The view and the command ---------------------------------------------------------------


def law() -> LawRecord:
    return LawRecord(
        procedure_id=AI_ACT, title="Artificial Intelligence Act", status="completed", coverage=()
    )


def test_the_view_records_its_method_and_round_trips_through_its_file(tmp_path: Path) -> None:
    amendments = [amendment("PE1-1", authors=(1,)), amendment("PE1-2", authors=(2,))]

    view = coordinated.build_coordination(law(), "run-1", amendments, MEPS, generated_at=LATER)
    path = coordinated.write_coordination(view, tmp_path)

    assert (view.procedure_id, view.slug, view.title, view.run_id) == (
        AI_ACT,
        SLUG,
        "Artificial Intelligence Act",
        "run-1",
    )
    assert (view.method, view.generated_at, view.limitations) == (
        coordinated.METHOD,
        LATER,
        # The test amendments record no tabling-day groups, as an older bundle's.
        (*coordinated.LIMITATIONS, TABLING_DAY_GROUPS, LATEST_SPELL_FALLBACK),
    )
    assert (view.min_inserted_words, view.shingle_words, view.similarity_threshold) == (
        coordinated.MIN_INSERTED_WORDS,
        coordinated.SHINGLE_WORDS,
        coordinated.SIMILARITY_THRESHOLD,
    )
    assert len(view.clusters) == 1
    assert path == tmp_path / coordinated.VIEW_FILE
    assert CoordinatedView.model_validate_json(path.read_bytes()) == view


def test_clusters_are_read_back_by_slug_and_a_broken_file_is_an_error(tmp_path: Path) -> None:
    assert coordinated.read_coordination(tmp_path, SLUG) is None
    assert coordinated.cross_group_clusters(tmp_path, SLUG) is None
    bundle = tmp_path / "laws" / SLUG
    bundle.mkdir(parents=True)
    amendments = [
        amendment("PE1-1", authors=(1,)),
        amendment("PE1-2", authors=(2,)),
        # A second cluster, tabled twice by one group: built, and not counted as crossing.
        amendment("PE1-3", " ".join(f"other{n}" for n in range(30)), authors=(1,)),
        amendment("PE1-4", " ".join(f"other{n}" for n in range(30)), authors=(3,)),
    ]
    view = coordinated.build_coordination(law(), "run-1", amendments, MEPS, generated_at=LATER)
    coordinated.write_coordination(view, bundle)

    assert coordinated.read_coordination(tmp_path, SLUG) == view
    assert [cluster.cross_group for cluster in view.clusters] == [True, False]
    assert coordinated.cross_group_clusters(tmp_path, SLUG) == 1

    (bundle / coordinated.VIEW_FILE).write_text("{}")
    with pytest.raises(coordinated.CoordinationError, match="invalid"):
        coordinated.read_coordination(tmp_path, SLUG)


def coordinated_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`test_collect`'s world with the draft tabled by a PPE and an S&D Member."""
    world = make_world(tmp_path)
    write_dump(
        world.inputs.committee_amendments,
        [
            committee_record(id="PE7-1", seq=1, old=[BASE], new=[f"{BASE} {DRAFT}"], meps=[1]),
            committee_record(
                id="PE7-2",
                seq=2,
                committee=["ITRE"],
                date="2022-03-31T00:00:00",
                old=[BASE],
                new=[f"{BASE} {variant(last=1)}"],
                meps=[2],
            ),
            committee_record(id="PE7-3", seq=3),
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


def test_the_command_collects_lists_the_clusters_and_writes_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    coordinated_world(tmp_path, monkeypatch)

    status = cli.main(["coordinated", AI_ACT, "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    path = tmp_path / "laws" / SLUG / coordinated.VIEW_FILE
    assert status == 0
    assert "\nCollected 2021/0106(COD) Artificial Intelligence Act in " in output
    assert (
        "Coordinated amendments: 1 of 1 clusters span political groups "
        "(4 amendments: 2 compared, 2 too short, 0 not comparable)\n"
        "  1. 2 amendments, PPE/S&D, at least 30 inserted words, least similar pair 0.93\n"
        f"     am:{SLUG}:ENVI:PE7-1  2022-01-25  [PPE]  Proposal for a regulation - Recital 1\n"
        f"     am:{SLUG}:ITRE:PE7-2  2022-03-31  [S&D]  Proposal for a regulation - Recital 1\n"
        f'     "{DRAFT[: cli.QUOTE_CHARACTERS]}"\n'
        f"clusters: {path}\n"
    ) in output
    view = CoordinatedView.model_validate_json(path.read_bytes())
    assert view.run_id == StageStore(path.parent).current().run_id  # pyright: ignore[reportOptionalMemberAccess]
    assert [len(cluster.members) for cluster in view.clusters] == [2]


def test_the_command_keeps_the_bundle_when_the_clusters_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    coordinated_world(tmp_path, monkeypatch)

    def broken(_view: CoordinatedView, bundle: Path) -> Path:
        raise PipelineError(f"cannot write in {bundle.name}")

    monkeypatch.setattr(cli, "write_coordination", broken)

    status = cli.main(["coordinated", AI_ACT, "--data-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert status == 1
    assert "Coordinated amendments" not in captured.out
    assert captured.err == (
        f"error: cannot write in {SLUG}\n"
        "The collected bundle is kept; no cluster file was written.\n"
    )
    assert StageStore(tmp_path / "laws" / SLUG).current() is not None
    assert not (tmp_path / "laws" / SLUG / coordinated.VIEW_FILE).exists()


# --- The atlas command and the API -----------------------------------------------------------


def test_the_atlas_command_writes_the_clusters_beside_the_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    coordinated_world(tmp_path, monkeypatch)

    status = cli.main(["atlas", AI_ACT, "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    path = tmp_path / "laws" / SLUG / coordinated.VIEW_FILE
    assert status == 0
    assert (
        "Coordinated amendments: 1 of 1 clusters span political groups "
        "(4 amendments: 2 compared, 2 too short, 0 not comparable)\n"
    ) in output
    assert f"clusters: {path}\n" in output
    written = CoordinatedView.model_validate_json(path.read_bytes())
    view = pipeline.read_view(tmp_path, SLUG)
    assert view is not None
    # One run, one clock: the clusters belong to the view they are served beside.
    assert (written.run_id, written.generated_at) == (view.run_id, view.generated_at)

    read = coordinated.read_coordination(tmp_path, SLUG)
    assert read == written
    body = json.loads(written.model_dump_json())
    assert set(body) == {
        "schema_version",
        "procedure_id",
        "slug",
        "title",
        "run_id",
        "generated_at",
        "method",
        "min_inserted_words",
        "shingle_words",
        "similarity_threshold",
        "counts",
        "clusters",
        "limitations",
    }
    (cluster,) = body["clusters"]
    assert (cluster["cross_group"], cluster["political_groups"]) == (True, ["PPE", "S&D"])
    assert set(cluster["members"][0]) == {
        "amendment_id",
        "stage",
        "committee",
        "tabled_on",
        "target_provision",
        "author_ids",
        "author_names",
        "political_groups",
        "inserted",
    }
    assert coordinated.cross_group_clusters(tmp_path, SLUG) == 1


def test_reading_unknown_and_broken_clusters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert coordinated.read_coordination(tmp_path, SLUG) is None

    coordinated_world(tmp_path, monkeypatch)
    assert cli.main(["atlas", AI_ACT, "--data-root", str(tmp_path)]) == 0
    (tmp_path / "laws" / SLUG / coordinated.VIEW_FILE).write_text("{}")
    with pytest.raises(coordinated.CoordinationError, match="are invalid"):
        coordinated.read_coordination(tmp_path, SLUG)
    # A broken cluster file does not touch the law's own view.
    assert pipeline.read_view(tmp_path, SLUG) is not None
