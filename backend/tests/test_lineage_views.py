"""Lineage views read back for the API, the routes, and the fixture the frontend tests read.

The world is `test_pipeline`'s matching world: an amendment inserts a rare phrase that a
consultation submission, dated before it, also asks for. As collected, the final act does
not hold the phrase, so it is tabled wording; `adopted_world` adds a final-act provision that
says it, so it becomes adopted wording with an origin.
"""

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from test_pipeline import LATER, RARE, SLUG, collected, matching_world

from influence.api import create_app
from influence.schemas.atlas import ArticleVersion
from influence.schemas.lineage import LineageView
from influence.services import lineage_views
from influence.services.lineage_assembly import VIEW_FILE, build_lineage, write_lineage
from influence.services.pipeline import Collected, PipelineError

ADOPTED = f"Providers shall keep the logs {RARE}."
# The frontend's tests read this view, so the TypeScript types are checked against real JSON.
# Regenerate after a contract change: uv run --directory backend --locked python
# tests/test_lineage_views.py
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


def built(tmp_path: Path) -> LineageView:
    view = build_lineage(adopted_world(tmp_path), generated_at=LATER)
    write_lineage(view, tmp_path / "laws" / SLUG)
    return view


def render_fixture() -> str:
    with TemporaryDirectory() as directory:
        view = build_lineage(adopted_world(Path(directory)), generated_at=LATER)
    return json.dumps(view.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def test_the_committed_frontend_fixture_is_the_adopted_worlds_view() -> None:
    assert FRONTEND_FIXTURE.read_text(encoding="utf-8") == render_fixture()


def test_the_fixture_holds_an_adopted_phrase_with_an_earlier_submission() -> None:
    """The frontend tests rely on this shape; a world change that loses it fails here first."""
    view = LineageView.model_validate_json(FRONTEND_FIXTURE.read_bytes())
    (phrase,) = view.adopted_phrases
    assert phrase.text.endswith(RARE)
    (origin,) = view.origins
    assert (origin.phrase_id, origin.counts_as_origin) == (phrase.phrase_id, True)
    assert view.credits


# --- On disk ------------------------------------------------------------------------------


def test_a_written_view_is_read_back_equal_and_listed(tmp_path: Path) -> None:
    view = built(tmp_path)

    assert lineage_views.read_lineage_view(tmp_path, SLUG) == view
    (summary,) = lineage_views.list_lineage_views(tmp_path).laws
    assert (summary.slug, summary.title, summary.status) == (
        SLUG,
        "Artificial Intelligence Act",
        "computed",
    )
    counts = view.counts
    assert (
        summary.adopted_phrases,
        summary.amendments_adopting,
        summary.documents_with_origin,
    ) == (
        counts.adopted_phrases,
        counts.amendments_adopting,
        counts.documents_with_origin,
    )


def test_absent_and_invalid_lineage_views(tmp_path: Path) -> None:
    assert lineage_views.read_lineage_view(tmp_path, SLUG) is None
    assert lineage_views.list_lineage_views(tmp_path).laws == ()
    (tmp_path / "laws" / SLUG).mkdir(parents=True)
    (tmp_path / "laws" / SLUG / VIEW_FILE).write_text("{}")
    with pytest.raises(PipelineError, match="invalid"):
        lineage_views.read_lineage_view(tmp_path, SLUG)


# --- The API --------------------------------------------------------------------------------


def test_the_api_lists_built_laws_and_serves_a_lineage_view(tmp_path: Path) -> None:
    view = built(tmp_path)
    client = TestClient(create_app(atlas_data_root=tmp_path))

    listing = client.get("/api/v1/lineage")
    served = client.get(f"/api/v1/lineage/{SLUG}")

    assert listing.status_code == 200
    assert listing.json()["laws"][0]["slug"] == SLUG
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
    (tmp_path / "laws" / SLUG / VIEW_FILE).write_text("{}")
    assert client.get(f"/api/v1/lineage/{SLUG}").status_code == 500
    assert client.get("/api/v1/lineage").status_code == 500


if __name__ == "__main__":
    FRONTEND_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FRONTEND_FIXTURE.write_text(render_fixture(), encoding="utf-8", newline="\n")
    print(f"Wrote the lineage view fixture to {FRONTEND_FIXTURE}")
