"""
Contract tests for the HTTP API: the exact responses and OpenAPI document the frontend
depends on.
"""

from importlib.metadata import version
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from influence.api import create_app
from influence.dependencies import get_demo_service


def test_health_returns_ok_and_installed_version() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": version("influence")}


def test_openapi_documents_health_response_schema() -> None:
    document = TestClient(create_app()).get("/openapi.json").json()

    assert document["info"] == {"title": "Influence Graph API", "version": version("influence")}
    ok_response = document["paths"]["/health"]["get"]["responses"]["200"]
    assert ok_response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Health"
    }
    health = document["components"]["schemas"]["Health"]
    assert health["properties"] == {
        "status": {"type": "string", "const": "ok", "title": "Status"},
        "version": {"type": "string", "title": "Version"},
    }
    assert health["required"] == ["status", "version"]


def test_health_does_not_require_demo_dataset(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = TestClient(create_app(data_dir=tmp_path / "absent"))

    assert client.get("/health").status_code == 200
    response = client.get("/api/v1/demo")
    assert response.status_code == 503
    assert response.json() == {
        "detail": {"code": "dataset_unavailable", "message": "Dataset unavailable"}
    }
    assert "Demo dataset unavailable" in caplog.text


def test_cors_allows_only_local_frontend() -> None:
    client = TestClient(create_app())
    local = client.options(
        "/api/v1/demo",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    external = client.options(
        "/api/v1/demo",
        headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
    )

    assert local.status_code == 200
    assert local.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert external.status_code == 400

    score_preflight = client.options(
        "/api/v1/score",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert score_preflight.status_code == 200
    assert score_preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert "POST" in score_preflight.headers["access-control-allow-methods"]
    assert "content-type" in score_preflight.headers["access-control-allow-headers"].lower()


def test_amendment_query_bounds_reject_invalid_requests() -> None:
    app = create_app()
    app.dependency_overrides[get_demo_service] = lambda: None
    client = TestClient(app)

    for query in ("offset=-1", "limit=0", "limit=101", f"q={'a' * 201}"):
        response = client.get(f"/api/v1/amendments?{query}")
        assert response.status_code == 422


def test_score_route_returns_computed_result_and_validates_input() -> None:
    client = TestClient(create_app())
    payload = {
        "amendment": {"old": "The controller may notify.", "new": "The controller shall notify."},
        "submission": {"old": "The controller may notify.", "new": "The controller shall notify."},
    }

    response = client.post("/api/v1/score", json=payload)
    assert response.status_code == 200
    assert response.json()["score"] == 1.0
    assert response.json()["score_type"] == "lexical_similarity"

    invalid = client.post("/api/v1/score", json={"amendment": payload["amendment"]})
    assert invalid.status_code == 422
