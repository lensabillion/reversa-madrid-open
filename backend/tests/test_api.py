"""Contract tests for the HTTP API: the health route, its OpenAPI shape and CORS."""

from importlib.metadata import version

from fastapi.testclient import TestClient

from influence.api import create_app


def test_health_returns_ok_and_installed_version() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": version("influence")}


def test_openapi_documents_health_response_schema() -> None:
    document = TestClient(create_app()).get("/openapi.json").json()

    assert document["info"] == {"title": "Influence Atlas API", "version": version("influence")}
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


def test_only_view_routes_remain() -> None:
    paths = TestClient(create_app()).get("/openapi.json").json()["paths"]

    assert set(paths) == {
        "/health",
        "/api/v1/atlas",
        "/api/v1/atlas/{slug}",
        "/api/v1/atlas/{slug}/coordinated",
        "/api/v1/atlas/{slug}/findings",
        "/api/v1/lineage",
        "/api/v1/lineage/{slug}",
    }
    assert {method for path in paths.values() for method in path} == {"get"}


def test_cors_allows_only_local_frontend() -> None:
    client = TestClient(create_app())
    local = client.options(
        "/api/v1/atlas",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    external = client.options(
        "/api/v1/atlas",
        headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
    )

    assert local.status_code == 200
    assert local.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert external.status_code == 400
