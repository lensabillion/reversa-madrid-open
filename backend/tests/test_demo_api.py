"""HTTP contracts for browsing a small public-style LobbyPlag snapshot."""

from pathlib import Path

from demo_fixture import write_dataset
from fastapi.testclient import TestClient

from influence.api import create_app


def test_demo_routes_present_source_data_and_pagination(tmp_path: Path) -> None:
    write_dataset(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))

    overview = client.get("/api/v1/demo")
    assert overview.status_code == 200
    assert overview.json()["amendments"] == 2
    assert overview.json()["verified_links"] == 1

    page = client.get("/api/v1/amendments?offset=0&limit=1")
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert len(page.json()["items"]) == 1
    assert page.json()["limit"] == 1

    verified = client.get("/api/v1/amendments?verified_only=true")
    assert verified.status_code == 200
    assert [item["id"] for item in verified.json()["items"]] == ["a1"]

    detail = client.get("/api/v1/amendments/a1")
    assert detail.status_code == 200
    assert detail.json()["amendment"]["id"] == "a1"
    assert detail.json()["sources"][0]["historically_verified"] is True

    assert client.get("/api/v1/amendments/a1/graph").status_code == 404

    organizations = client.get("/api/v1/organizations")
    assert organizations.status_code == 200
    assert organizations.json()["items"][0]["name"] == "Example association"


def test_missing_amendment_and_invalid_dataset_are_safe_errors(tmp_path: Path) -> None:
    write_dataset(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))

    missing = client.get("/api/v1/amendments/unknown")
    assert missing.status_code == 404
    assert missing.json() == {"detail": {"code": "entity_not_found", "message": "Entity not found"}}

    (tmp_path / "plags.json").write_text("not json")
    invalid = TestClient(create_app(data_dir=tmp_path)).get("/api/v1/demo")
    assert invalid.status_code == 503
    assert invalid.json() == {"detail": {"code": "dataset_invalid", "message": "Dataset invalid"}}
