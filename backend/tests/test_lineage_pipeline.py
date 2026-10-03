"""The lineage assembly over a collected law, its file, its API and the lineage command.

The world is `test_pipeline`'s matching world: an amendment inserts a rare phrase that a
consultation submission, dated before it, also asks for. As collected, the final act does
not hold the phrase, so it is tabled wording; `adopted_world` adds a final-act provision that
says it, so it becomes adopted wording.
"""

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from test_collect import scripted_cli
from test_pipeline import AI_ACT, LATER, RARE, SLUG, collected, matching_world

from influence import cli
from influence.api import create_app
from influence.extraction.records import StageStore
from influence.schemas.atlas import ArticleVersion, span_matches
from influence.schemas.lineage import LineageView
from influence.services import lineage_pipeline
from influence.services.origin import OriginError
from influence.services.pipeline import Collected, PipelineError

ADOPTED = f"Providers shall keep the logs {RARE}."
# The frontend's tests read this view, so the TypeScript types are checked against real JSON.
# Regenerate after a contract change: uv run --directory backend --locked python
# tests/test_lineage_pipeline.py
FRONTEND_FIXTURE = Path(__file__).parent / "fixtures" / "lineage" / "view.json"


def adopted_world(tmp_path: Path) -> Collected:
    law = collected(matching_world(tmp_path))
    final = next(article for article in law.articles if article.stage == "final_act")
    logs = ArticleVersion(
        article_id="art:32024R1689:article-12",
        procedure_id=final.procedure_id,
        document_id=final.document_id,
        stage="final_act",
        provision="Article 12",
        kind="article",
        text=ADOPTED,
    )
    return replace(law, articles=(*law.articles, logs))


def test_wording_the_final_act_adopted_is_traced_to_its_amendment_and_an_earlier_submission(
    tmp_path: Path,
) -> None:
    law = adopted_world(tmp_path)

    view = lineage_pipeline.build_lineage_view(law, generated_at=LATER)

    (phrase,) = view.adopted_phrases
    assert phrase.text == RARE
    (final_span,) = phrase.final_spans
    assert span_matches(final_span, ADOPTED)
    (adoption,) = view.adoptions
    assert adoption.amendment_id == "am:2021-0106-COD:ENVI:PE7-7"
    (origin,) = view.origins
    assert (origin.phrase_id, origin.document_id) == (phrase.phrase_id, "doc:hys_feedback:4")
    assert (origin.organisation, origin.precedes, origin.is_citation) == (
        "Acme Unknown Lobby",
        True,
        False,
    )
    assert view.tabled_phrases == ()
    assert view.credits[0].phrases == 1
    counts = view.counts
    # Four comments and one attachment are read; the proposal and the final act never are.
    assert (counts.adopted_phrases, counts.amendments_adopting, counts.amendments) == (1, 1, 3)
    assert (counts.documents_read, counts.documents_with_origin) == (5, 1)
    assert (view.slug, view.method, view.coverage) == (
        SLUG,
        lineage_pipeline.METHOD,
        law.law.coverage,
    )
    assert view.limitations[: len(lineage_pipeline.LIMITATIONS)] == lineage_pipeline.LIMITATIONS


def test_inserted_wording_that_was_not_adopted_is_a_tabled_phrase_with_its_origin(
    tmp_path: Path,
) -> None:
    view = lineage_pipeline.build_lineage_view(
        collected(matching_world(tmp_path)), generated_at=LATER
    )

    assert view.adopted_phrases == ()
    assert view.adoptions == ()
    (tabled,) = view.tabled_phrases
    assert (tabled.text, tabled.amendment_ids) == (RARE, ("am:2021-0106-COD:ENVI:PE7-7",))
    (origin,) = view.origins
    assert origin.phrase_id == tabled.phrase_id
    assert view.counts.documents_with_origin == 1


def test_an_inconsistent_origin_search_is_an_explicit_pipeline_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object, **_kwargs: object) -> object:
        raise OriginError("phrase:x is carried by no amendment")

    monkeypatch.setattr(lineage_pipeline, "find_origins", broken)

    with pytest.raises(PipelineError, match="carried by no amendment"):
        lineage_pipeline.build_lineage_view(adopted_world(tmp_path), generated_at=LATER)


def render_fixture() -> str:
    with TemporaryDirectory() as directory:
        view = lineage_pipeline.build_lineage_view(
            adopted_world(Path(directory)), generated_at=LATER
        )
    return json.dumps(view.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def test_the_committed_frontend_fixture_is_the_adopted_worlds_view() -> None:
    assert FRONTEND_FIXTURE.read_text(encoding="utf-8") == render_fixture()


# --- On disk ------------------------------------------------------------------------------


def test_the_view_is_written_read_back_equal_and_listed(tmp_path: Path) -> None:
    view = lineage_pipeline.build_lineage_view(adopted_world(tmp_path), generated_at=LATER)

    path = lineage_pipeline.write_lineage_view(view, tmp_path / "laws" / SLUG)

    assert json.loads(path.read_bytes())["schema_version"] == "lineage-1"
    assert lineage_pipeline.read_lineage_view(tmp_path, SLUG) == view
    (summary,) = lineage_pipeline.list_lineage_views(tmp_path).laws
    assert (summary.slug, summary.title, summary.adopted_phrases) == (
        SLUG,
        "Artificial Intelligence Act",
        1,
    )
    assert (summary.amendments_adopting, summary.documents_with_origin) == (1, 1)


def test_absent_and_invalid_lineage_views(tmp_path: Path) -> None:
    assert lineage_pipeline.read_lineage_view(tmp_path, SLUG) is None
    assert lineage_pipeline.list_lineage_views(tmp_path).laws == ()
    (tmp_path / "laws" / SLUG).mkdir(parents=True)
    (tmp_path / "laws" / SLUG / lineage_pipeline.VIEW_FILE).write_text("{}")
    with pytest.raises(PipelineError, match="invalid"):
        lineage_pipeline.read_lineage_view(tmp_path, SLUG)


# --- The API --------------------------------------------------------------------------------


def test_the_api_lists_built_laws_and_serves_a_lineage_view(tmp_path: Path) -> None:
    view = lineage_pipeline.build_lineage_view(adopted_world(tmp_path), generated_at=LATER)
    lineage_pipeline.write_lineage_view(view, tmp_path / "laws" / SLUG)
    client = TestClient(create_app(atlas_data_root=tmp_path))

    listing = client.get("/api/v1/lineage")
    served = client.get(f"/api/v1/lineage/{SLUG}")

    assert listing.status_code == 200
    assert listing.json()["laws"][0]["adopted_phrases"] == 1
    assert served.status_code == 200
    assert LineageView.model_validate(served.json()) == view


def test_the_api_answers_unknown_malformed_and_broken_lineage_views(tmp_path: Path) -> None:
    client = TestClient(create_app(atlas_data_root=tmp_path))

    assert client.get("/api/v1/lineage").json() == {"laws": []}
    missing = client.get("/api/v1/lineage/2099-0001-COD")
    assert missing.status_code == 404
    assert "make lineage" in missing.json()["detail"]
    assert client.get("/api/v1/lineage/not-a-law").status_code == 422
    (tmp_path / "laws" / SLUG).mkdir(parents=True)
    (tmp_path / "laws" / SLUG / lineage_pipeline.VIEW_FILE).write_text("{}")
    assert client.get(f"/api/v1/lineage/{SLUG}").status_code == 500
    assert client.get("/api/v1/lineage").status_code == 500


# --- The command ----------------------------------------------------------------------------


def test_the_lineage_command_collects_builds_and_points_at_the_explorer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world = matching_world(tmp_path)
    scripted_cli(monkeypatch, world)

    status = cli.main(["lineage", AI_ACT, "--data-root", str(tmp_path)])

    output = capsys.readouterr().out
    assert status == 0
    assert "Lineage: 0 adopted phrases in 0 of 3 amendments; 1 tabled phrases; " in output
    assert "1 origin quotations in 1 of 5 submissions" in output
    assert f"explorer: http://localhost:3000/lineage?law={SLUG}" in output
    assert lineage_pipeline.read_lineage_view(tmp_path, SLUG) is not None


def test_the_lineage_command_keeps_the_bundle_when_the_view_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world = matching_world(tmp_path)
    scripted_cli(monkeypatch, world)

    def broken(_collected: Collected, *, generated_at: datetime) -> LineageView:
        raise PipelineError(f"no lineage at {generated_at:%H}")

    monkeypatch.setattr(cli, "build_lineage_view", broken)

    status = cli.main(["lineage", AI_ACT, "--data-root", str(tmp_path)])

    error = capsys.readouterr().err
    assert status == 1
    assert "no lineage at" in error
    assert "no lineage view was written" in error
    assert StageStore(tmp_path / "laws" / SLUG).current() is not None
    assert lineage_pipeline.read_lineage_view(tmp_path, SLUG) is None


if __name__ == "__main__":
    FRONTEND_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FRONTEND_FIXTURE.write_text(render_fixture(), encoding="utf-8", newline="\n")
    print(f"Wrote the lineage view fixture to {FRONTEND_FIXTURE}")
