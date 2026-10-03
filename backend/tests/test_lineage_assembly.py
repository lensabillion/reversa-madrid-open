"""Lineage assembly and `influence lineage`: one view, written atomically, honest when empty."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from atlas_fixture import build_fixture
from test_coordinated import AI_ACT, SLUG, coordinated_world
from test_lineage import FINAL, NEW, PROPOSAL, amendment, mep
from test_origin import document

from influence import cli
from influence.schemas.atlas import Actor, ArticleVersion, Passage, SourceSpan
from influence.schemas.lineage import LineageCounts, LineageView
from influence.services import lineage_assembly
from influence.services.lineage_assembly import build_lineage, write_lineage
from influence.services.pipeline import Collected, PipelineError

NOW = datetime(2099, 12, 1, tzinfo=UTC)
ACME = Actor(
    actor_id="actor:tr:123456789012-34",
    kind="organisation",
    name="Acme Association",
    resolution="register_id",
    register_id="123456789012-34",
)


def collected(
    *,
    articles: tuple[ArticleVersion, ...] = (PROPOSAL, FINAL),
    with_documents: bool = True,
) -> Collected:
    fixture = build_fixture()
    early = document("1", "We ask: " + NEW, published=datetime(2099, 1, 1, tzinfo=UTC))
    late = document("2", NEW, kind="hys_feedback", published=datetime(2099, 9, 1, tzinfo=UTC))
    own = document("3", NEW, kind="cellar", title="The final act itself")
    lost = document("4", "Also: " + " ".join(f"lost{i}" for i in range(12)))
    documents = (early, late, own, lost) if with_documents else ()
    passage = Passage(
        passage_id="passage:a:1",
        procedure_id="2099/0001(COD)",
        document_id=early[0].document_id,
        actor_id=ACME.actor_id,
        span=SourceSpan(record_id=early[0].document_id, start=0, end=2, text="We"),
        submitted_at=None,
    )
    return Collected(
        manifest=fixture.manifests[0],
        law=fixture.laws[0],
        documents=tuple(source for source, _ in documents),
        document_texts=tuple(text for _, text in documents),
        passages=(passage,),
        actors=(ACME, mep(1, "PPE"), mep(2, "S&D")),
        amendments=(
            amendment(1, NEW, authors=("actor:mep:1",)),
            amendment(2, " ".join(f"lost{i}" for i in range(12)), authors=("actor:mep:2",)),
        ),
        articles=articles,
    )


def test_the_view_holds_adoption_origins_tabled_wording_and_counts() -> None:
    view = build_lineage(collected(), generated_at=NOW)
    assert (view.status, view.reason, view.generated_at) == ("computed", None, NOW)
    assert view.run_id == build_fixture().manifests[0].run_id
    (phrase,) = view.adopted_phrases
    adopted = {o.document_id: o for o in view.origins if o.phrase_id == phrase.phrase_id}
    # The law's own text is never searched; the early attachment came first, the late
    # comment did not.
    assert set(adopted) == {"doc:hys_attachment:1", "doc:hys_feedback:2"}
    assert adopted["doc:hys_attachment:1"].counts_as_origin
    assert adopted["doc:hys_attachment:1"].organisation == "Acme Association"
    assert not adopted["doc:hys_feedback:2"].counts_as_origin
    (tabled,) = view.tabled_phrases
    assert tabled.amendment_ids == ("am:2099-0001-COD:IMCO:2",)
    counts = view.counts
    assert (counts.documents_read, counts.documents_with_origin) == (3, 2)
    assert (counts.adopted_phrases, counts.amendments_adopting, counts.amendments) == (1, 1, 2)
    assert counts.linked_units is not None
    assert view.limitations[: len(lineage_assembly.LIMITATIONS)] == lineage_assembly.LIMITATIONS
    member = next(c for c in view.credits if c.holder_id == "actor:mep:1")
    assert (member.amendments, member.amendments_tabled) == (1, 1)


def test_without_consultation_text_the_origins_are_unknown_not_zero() -> None:
    view = build_lineage(collected(with_documents=False), generated_at=NOW)
    assert (view.counts.documents_read, view.counts.documents_with_origin) == (None, None)
    assert view.origins == ()
    assert "No consultation document text was collected; origins are unknown." in view.limitations


def test_without_a_final_act_the_view_is_unknown_with_its_reason() -> None:
    view = build_lineage(collected(articles=(PROPOSAL,)), generated_at=NOW)
    assert view.status == "unknown"
    assert view.reason is not None
    assert (view.counts.adopted_phrases, view.counts.documents_read) == (None, None)
    assert "Origins were not searched: adoption could not be computed." in view.limitations


def test_the_view_is_written_atomically_and_reads_back(tmp_path: Path) -> None:
    view = build_lineage(collected(), generated_at=NOW)
    path = write_lineage(view, tmp_path)
    assert path == tmp_path / lineage_assembly.VIEW_FILE
    assert LineageView.model_validate_json(path.read_bytes()) == view
    assert list(tmp_path.iterdir()) == [path]


def test_the_command_collects_traces_and_writes_the_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    coordinated_world(tmp_path, monkeypatch)

    status = cli.main(["lineage", AI_ACT, "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    path = tmp_path / "laws" / SLUG / lineage_assembly.VIEW_FILE
    assert status == 0
    assert "\nLineage: " in output
    assert output.endswith(f"lineage: {path}\n")
    view = LineageView.model_validate_json(path.read_bytes())
    assert view.procedure_id == AI_ACT


def _view(**changes: object) -> LineageView:
    base = build_lineage(collected(), generated_at=NOW)
    return base.model_copy(update=changes)


@pytest.mark.parametrize(
    ("view", "expected"),
    [
        (
            _view(
                status="unknown",
                reason="The final act's text was not collected.",
                adopted_phrases=(),
                adoptions=(),
                origins=(),
                credits=(),
            ),
            "Lineage: unknown (The final act's text was not collected.)\n",
        ),
        (
            _view(counts=LineageCounts(amendments=2, adopted_phrases=0, amendments_adopting=0)),
            "  origins unknown (no consultation text)\n",
        ),
        (
            _view(),
            "  2 of 3 consultation documents say adopted or tabled wording first\n"
            "  Member 1: 1 of 1 amendments adopted, 1 phrase(s) (0 joint)\n",
        ),
    ],
)
def test_the_command_prints_what_is_known_and_says_what_is_not(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    view: LineageView,
    expected: str,
) -> None:
    coordinated_world(tmp_path, monkeypatch)

    def fixed(_collected: Collected, *, generated_at: datetime) -> LineageView:
        assert generated_at.tzinfo is not None
        return view

    monkeypatch.setattr(cli, "build_lineage", fixed)

    assert cli.main(["lineage", AI_ACT, "--data-root", str(tmp_path)]) == 0
    assert expected in capsys.readouterr().out


def test_the_command_keeps_the_bundle_when_the_lineage_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    coordinated_world(tmp_path, monkeypatch)

    def broken(_view: LineageView, bundle: Path) -> Path:
        raise PipelineError(f"cannot write in {bundle.name}")

    monkeypatch.setattr(cli, "write_lineage", broken)

    status = cli.main(["lineage", AI_ACT, "--data-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert status == 1
    assert captured.err == (
        f"error: cannot write in {SLUG}\n"
        "The collected bundle is kept; no lineage file was written.\n"
    )
    assert not (tmp_path / "laws" / SLUG / lineage_assembly.VIEW_FILE).exists()
