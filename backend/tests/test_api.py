"""
Contract tests for the HTTP API: the exact responses and OpenAPI document the frontend
depends on.
"""

from importlib.metadata import version

from fastapi.testclient import TestClient

from influence.api import create_app


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
