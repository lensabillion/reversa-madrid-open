"""Contract tests for the HTTP API: the health route, its OpenAPI shape, CORS and gzip."""

import gzip
import shutil
from importlib.metadata import version
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from influence.api import GZIP_MINIMUM_BYTES, create_app
from influence.services.lineage_assembly import VIEW_FILE


def test_health_returns_ok_and_installed_version() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": version("influence")}


def test_openapi_documents_health_response_schema() -> None:
    document = TestClient(create_app()).get("/openapi.json").json()

    assert document["info"] == {"title": "influence API", "version": version("influence")}
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
        "/api/v1/lineage",
        "/api/v1/lineage/{slug}",
    }
    assert {method for path in paths.values() for method in path} == {"get"}


def test_cors_allows_only_local_frontend() -> None:
    client = TestClient(create_app())
    local = client.options(
        "/api/v1/lineage",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    external = client.options(
        "/api/v1/lineage",
        headers={"Origin": "https://example.com", "Access-Control-Request-Method": "GET"},
    )

    assert local.status_code == 200
    assert local.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert external.status_code == 400


# --- Compression --------------------------------------------------------------------------

# The committed lineage view the frontend tests read; `test_lineage_views` keeps it equal to
# what the pipeline writes, so it is a real view of the current contract.
VIEW_FIXTURE = Path(__file__).parent / "fixtures" / "lineage" / "view.json"
VIEW_SLUG = "2021-0106-COD"


@pytest.fixture
def served(tmp_path: Path) -> TestClient:
    """An app over a data root that holds the committed lineage view."""
    law = tmp_path / "laws" / VIEW_SLUG
    law.mkdir(parents=True)
    shutil.copyfile(VIEW_FIXTURE, law / VIEW_FILE)
    return TestClient(create_app(tmp_path))


def test_a_view_is_gzipped_only_when_the_client_accepts_gzip(served: TestClient) -> None:
    """The bytes on the wire are gzip, and they decompress to the plain answer.

    TestClient (httpx) sends `Accept-Encoding: gzip, deflate` by default and decompresses
    `response.content`, so the plain request sends `identity` explicitly and the gzip request
    reads the undecoded body through `iter_raw`; `num_bytes_downloaded` counts the bytes
    that crossed the transport.
    """
    url = f"/api/v1/lineage/{VIEW_SLUG}"
    plain = served.get(url, headers={"Accept-Encoding": "identity"})
    with served.stream("GET", url, headers={"Accept-Encoding": "gzip"}) as compressed:
        wire = b"".join(compressed.iter_raw())

    assert plain.status_code == compressed.status_code == 200
    assert "content-encoding" not in plain.headers
    assert plain.num_bytes_downloaded == len(plain.content)
    assert compressed.headers["content-encoding"] == "gzip"
    assert compressed.headers["vary"] == "Accept-Encoding"
    assert int(compressed.headers["content-length"]) == compressed.num_bytes_downloaded
    assert compressed.num_bytes_downloaded == len(wire)
    assert gzip.decompress(wire) == plain.content
    # Repetitive JSON keys compress well: this view measures 0.36; the real AI Act view 0.13.
    assert len(wire) < 0.5 * len(plain.content)


@pytest.mark.parametrize(
    ("path", "status"),
    [("/health", 200), ("/api/v1/lineage", 200), ("/api/v1/lineage/2099-0001-COD", 404)],
)
def test_short_answers_stay_plain_even_when_gzip_is_accepted(
    served: TestClient, path: str, status: int
) -> None:
    """Below `GZIP_MINIMUM_BYTES` compression saves no packet, so the body goes out as is."""
    response = served.get(path, headers={"Accept-Encoding": "gzip"})

    assert response.status_code == status
    assert len(response.content) < GZIP_MINIMUM_BYTES
    assert "content-encoding" not in response.headers
    assert response.num_bytes_downloaded == len(response.content)
