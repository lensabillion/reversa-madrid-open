"""Part 8 · The explorer's law search and build API, over collect's scripted world.

No test reaches the network or sleeps: the build runs synchronously, or is held and
released by the test.
"""

import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_batch import SCRIPT
from test_collect import AI_ACT, NOW, ONGOING, World, make_world

from influence.api import create_app
from influence.extraction.layout import procedure_slug
from influence.services import law_search
from influence.services.law_search import LawService

type Work = Callable[[], None]


def client_for(root: Path, world: World | None, start: Callable[[Work], None]) -> TestClient:
    app = create_app(atlas_data_root=root)
    if world is not None:
        app.state.law_service = LawService(
            root, fetcher=world.fetcher, code_revision="test", clock=lambda: NOW, start=start
        )
    return TestClient(app)


def run_now(work: Work) -> None:
    work()


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return client_for(tmp_path, make_world(tmp_path, SCRIPT), run_now)


def test_a_common_name_is_found_with_what_is_built(client: TestClient) -> None:
    body = client.get("/api/v1/laws/search", params={"q": "Toy Safety"}).json()

    assert body["status"] == "found"
    assert body["message"] is None
    assert body["law"] == {
        "procedure_id": ONGOING,
        "title": "Toy Safety",
        "slug": procedure_slug(ONGOING),
        "has_lineage": False,
        "has_atlas": False,
        "build": None,
    }
    assert body["choices"] == [body["law"]]


def test_a_shared_title_is_ambiguous(client: TestClient) -> None:
    body = client.get("/api/v1/laws/search", params={"q": "Data Act"}).json()

    assert body["status"] == "ambiguous"
    assert body["law"] is None
    assert [c["procedure_id"] for c in body["choices"]] == ["2022/0047(COD)", "2023/0001(COD)"]
    assert "matches several procedures" in body["message"]


def test_unknown_text_and_numbers_outside_the_catalog_are_not_found(client: TestClient) -> None:
    text = client.get("/api/v1/laws/search", params={"q": "Zebra crossings"}).json()
    number = client.get("/api/v1/laws/search", params={"q": "2099/0001(COD)"}).json()

    assert (text["status"], text["law"], text["choices"]) == ("not_found", None, [])
    assert "No procedure title" in text["message"]
    assert number["status"] == "not_found"
    assert number["message"] == "2099/0001(COD) is not in the Parltrack dossiers catalog"


def test_an_empty_query_is_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/laws/search", params={"q": "   "}).status_code == 422
    assert client.get("/api/v1/laws/search").status_code == 422


def test_without_setup_search_and_build_answer_503(tmp_path: Path) -> None:
    client = client_for(tmp_path, None, run_now)
    message = "Run `make setup` first: the Parltrack dossiers catalog is missing"

    search = client.get("/api/v1/laws/search", params={"q": "AI Act"})
    build = client.post(f"/api/v1/laws/{procedure_slug(AI_ACT)}/build")

    assert (search.status_code, search.json()["detail"]) == (503, message)
    assert (build.status_code, build.json()["detail"]) == (503, message)


def test_a_build_collects_runs_the_steps_and_search_then_shows_them(
    tmp_path: Path, client: TestClient
) -> None:
    slug = procedure_slug(AI_ACT)

    started = client.post(f"/api/v1/laws/{slug}/build", json={"steps": ["atlas", "lineage"]})

    assert started.status_code == 202
    state = started.json()
    assert state["state"] == "done"
    assert (state["step"], state["error"]) == (None, None)
    assert state["steps"] == ["atlas", "lineage"]
    assert state["started_at"] == NOW.isoformat() == state["finished_at"]
    assert state["log"][1].startswith("Collecting without attachments")
    assert state["log"][-1] == "Done"
    assert client.get(f"/api/v1/laws/{slug}/build").json() == state
    found = client.get("/api/v1/laws/search", params={"q": AI_ACT}).json()["law"]
    assert (found["has_lineage"], found["has_atlas"], found["build"]) == (True, True, state)
    assert (tmp_path / "laws" / slug / "lineage.json").is_file()


def test_a_failing_build_is_failed_with_the_error_type(client: TestClient) -> None:
    # The script has no CELLAR answer for this procedure, so collect fails; the failure
    # is recorded in the state, never raised out of the thread.
    slug = procedure_slug("2023/0001(COD)")

    state = client.post(f"/api/v1/laws/{slug}/build").json()

    assert state["state"] == "failed"
    assert state["step"] == "collect"
    assert state["steps"] == ["atlas", "lineage"]
    assert state["error"].split(":")[0].endswith("Error")
    assert state["log"][-1] == f"Failed: {state['error']}"


def test_one_build_at_a_time_and_unknown_slugs(tmp_path: Path) -> None:
    held: list[Work] = []
    client = client_for(tmp_path, make_world(tmp_path, SCRIPT), held.append)
    slug = procedure_slug(ONGOING)

    first = client.post(f"/api/v1/laws/{slug}/build", json={"steps": ["coordinated"]})
    busy = client.post(f"/api/v1/laws/{procedure_slug(AI_ACT)}/build")
    queued = client.get(f"/api/v1/laws/{slug}/build").json()
    held.pop()()

    assert (first.status_code, first.json()["state"]) == (202, "queued")
    assert busy.status_code == 409
    assert (queued["state"], queued["step"]) == ("queued", None)
    assert client.get(f"/api/v1/laws/{slug}/build").json()["state"] == "done"
    assert client.post("/api/v1/laws/2099-0001-COD/build").status_code == 404
    assert client.get("/api/v1/laws/2099-0001-COD/build").status_code == 404
    assert client.post(f"/api/v1/laws/{slug}/build", json={"steps": []}).status_code == 422


def test_the_default_runner_runs_the_build_in_a_background_thread() -> None:
    ran = threading.Event()

    law_search._background(ran.set)  # pyright: ignore[reportPrivateUsage]

    assert ran.wait(timeout=10)
