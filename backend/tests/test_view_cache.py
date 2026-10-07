"""HTTP caching of the lineage views: Cache-Control, ETag, Last-Modified and 304.

The views are written by `test_lineage_views.built`, then their modification times are set
with `os.utime` so every validator is deterministic and a rewrite always moves the clock.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_lineage_views import built
from test_pipeline import SLUG

from influence.api import create_app
from influence.routers import lineage
from influence.routers.view_cache import DEFAULT_MAX_AGE, MAX_AGE_VARIABLE, max_age_from
from influence.schemas.lineage import LineageView
from influence.services import lineage_views
from influence.services.lineage_assembly import VIEW_FILE, write_lineage

OTHER = "2020-0361-COD"
# 2023-11-14 22:13:20 UTC plus 123456789 ns: the HTTP date keeps whole seconds only.
MTIME_NS = 1_700_000_000_123_456_789
MTIME_HTTP = "Tue, 14 Nov 2023 22:13:20 GMT"
LATER_MTIME_NS = MTIME_NS + 86_400 * 10**9
LATER_HTTP = "Wed, 15 Nov 2023 22:13:20 GMT"


def view_path(root: Path, slug: str = SLUG) -> Path:
    return root / "laws" / slug / VIEW_FILE


def touch(path: Path, mtime_ns: int) -> None:
    os.utime(path, ns=(mtime_ns, mtime_ns))


def world(root: Path) -> tuple[TestClient, LineageView]:
    view = built(root)
    touch(view_path(root), MTIME_NS)
    return TestClient(create_app(atlas_data_root=root)), view


def add_other(root: Path, view: LineageView, mtime_ns: int) -> None:
    write_lineage(view.model_copy(update={"slug": OTHER}), root / "laws" / OTHER)
    touch(view_path(root, OTHER), mtime_ns)


def matching(*tags: str) -> list[tuple[str, str]]:
    """One If-None-Match field per tag, so repeated fields are exercised too."""
    return [("If-None-Match", tag) for tag in tags]


# --- The variable ----------------------------------------------------------------------------


def test_the_max_age_defaults_accepts_whole_seconds_and_rejects_the_rest() -> None:
    assert max_age_from({}) == DEFAULT_MAX_AGE == 3600
    assert max_age_from({MAX_AGE_VARIABLE: "60"}) == 60
    assert max_age_from({MAX_AGE_VARIABLE: "0"}) == 0
    for bad in ("", "-1", "1.5", "+5", " 60", "an hour"):
        with pytest.raises(ValueError, match=f"^{MAX_AGE_VARIABLE} must be a whole number"):
            max_age_from({MAX_AGE_VARIABLE: bad})


def start_api(root: Path, max_age: str) -> subprocess.CompletedProcess[str]:
    """Import the app in a fresh interpreter, as uvicorn does, and print one header."""
    script = (
        "from fastapi.testclient import TestClient\n"
        "from influence.api import app\n"
        f"print(TestClient(app).get('/api/v1/lineage/{SLUG}').headers['cache-control'])\n"
    )
    env = {**os.environ, "INFLUENCE_DATA_ROOT": str(root), MAX_AGE_VARIABLE: max_age}
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=False
    )


def test_the_api_serves_the_configured_max_age_and_refuses_to_start_on_a_bad_one(
    tmp_path: Path,
) -> None:
    built(tmp_path)

    served = start_api(tmp_path, "60")
    refused = start_api(tmp_path, "-60")

    assert (served.returncode, served.stdout) == (0, "public, max-age=60\n"), served.stderr
    assert refused.returncode != 0
    assert f"ValueError: {MAX_AGE_VARIABLE} must be a whole number" in refused.stderr


# --- One view --------------------------------------------------------------------------------


def test_a_view_carries_cache_control_etag_and_last_modified(tmp_path: Path) -> None:
    client, view = world(tmp_path)

    served = client.get(f"/api/v1/lineage/{SLUG}")

    assert served.status_code == 200
    assert LineageView.model_validate(served.json()) == view
    assert served.headers["cache-control"] == f"public, max-age={lineage.VIEW_MAX_AGE}"
    assert served.headers["last-modified"] == MTIME_HTTP
    tag = served.headers["etag"]
    assert re.fullmatch(r'W/"[0-9a-f]{32}"', tag), tag
    assert client.get(f"/api/v1/lineage/{SLUG}").headers["etag"] == tag


def test_a_matching_if_none_match_answers_304_with_the_same_headers_and_no_body(
    tmp_path: Path,
) -> None:
    client, _ = world(tmp_path)
    url = f"/api/v1/lineage/{SLUG}"
    full = client.get(url)
    tag = full.headers["etag"]

    strong = tag.removeprefix("W/")
    for tags in ((tag,), (strong,), (f'"other", {tag}',), ('"other"', tag), ("*",)):
        cached = client.get(url, headers=matching(*tags))
        assert cached.status_code == 304, tags
        assert cached.content == b""
        assert "content-type" not in cached.headers
        for header in ("etag", "cache-control", "last-modified"):
            assert cached.headers[header] == full.headers[header], (tags, header)
    for tags in (('"other"',), (tag.strip('"'),), (f'"{tag}"',)):
        assert client.get(url, headers=matching(*tags)).status_code == 200, tags


def test_the_tag_is_the_same_for_the_gzip_and_the_plain_answer(tmp_path: Path) -> None:
    """One weak tag names both representations, so a client that got either revalidates.

    Vary tells caches the two answers differ by Accept-Encoding; a strong tag would have to
    differ too, which is why the tag is weak.
    """
    client, _ = world(tmp_path)
    url = f"/api/v1/lineage/{SLUG}"

    plain = client.get(url, headers={"Accept-Encoding": "identity"})
    compressed = client.get(url, headers={"Accept-Encoding": "gzip"})

    assert "content-encoding" not in plain.headers
    assert compressed.headers["content-encoding"] == "gzip"
    assert "accept-encoding" in compressed.headers["vary"].lower()
    assert plain.headers["etag"] == compressed.headers["etag"]
    assert plain.headers["etag"].startswith('W/"')
    revalidated = client.get(
        url, headers=[("Accept-Encoding", "gzip"), *matching(plain.headers["etag"])]
    )
    assert revalidated.status_code == 304
    assert "content-encoding" not in revalidated.headers


def test_rewriting_a_view_changes_its_etag(tmp_path: Path) -> None:
    client, view = world(tmp_path)
    url = f"/api/v1/lineage/{SLUG}"
    before = client.get(url).headers["etag"]

    write_lineage(view.model_copy(update={"title": "Rewritten"}), tmp_path / "laws" / SLUG)
    touch(view_path(tmp_path), LATER_MTIME_NS)
    after = client.get(url, headers=matching(before))

    assert after.status_code == 200
    assert after.json()["title"] == "Rewritten"
    assert after.headers["etag"] != before
    assert after.headers["last-modified"] == LATER_HTTP


def test_same_content_with_a_new_mtime_still_changes_the_etag(tmp_path: Path) -> None:
    client, _ = world(tmp_path)
    url = f"/api/v1/lineage/{SLUG}"
    before = client.get(url).headers["etag"]

    touch(view_path(tmp_path), MTIME_NS + 1)

    assert client.get(url, headers=matching(before)).status_code == 200


def test_a_rewrite_of_another_size_within_the_same_mtime_still_changes_the_etag(
    tmp_path: Path,
) -> None:
    """A coarse filesystem clock can give a rewrite the old mtime; the size still differs."""
    client, view = world(tmp_path)
    url = f"/api/v1/lineage/{SLUG}"
    before = client.get(url).headers["etag"]

    write_lineage(view.model_copy(update={"title": "Rewritten"}), tmp_path / "laws" / SLUG)
    touch(view_path(tmp_path), MTIME_NS)

    assert client.get(url, headers=matching(before)).status_code == 200


# --- The list --------------------------------------------------------------------------------


def test_the_list_carries_the_headers_and_answers_304(tmp_path: Path) -> None:
    client, view = world(tmp_path)
    add_other(tmp_path, view, LATER_MTIME_NS)

    listing = client.get("/api/v1/lineage")
    cached = client.get("/api/v1/lineage", headers=matching(listing.headers["etag"]))

    assert listing.status_code == 200
    assert [law["slug"] for law in listing.json()["laws"]] == [SLUG, OTHER]
    assert listing.headers["cache-control"] == f"public, max-age={lineage.VIEW_MAX_AGE}"
    assert listing.headers["last-modified"] == LATER_HTTP
    assert (cached.status_code, cached.content) == (304, b"")
    assert cached.headers["etag"] == listing.headers["etag"]


def test_the_list_etag_changes_when_a_view_is_added_rewritten_or_removed(
    tmp_path: Path,
) -> None:
    client, view = world(tmp_path)

    def tag() -> str:
        return client.get("/api/v1/lineage").headers["etag"]

    alone = tag()
    add_other(tmp_path, view, LATER_MTIME_NS)
    both = tag()
    touch(view_path(tmp_path, OTHER), LATER_MTIME_NS + 1)
    rewritten = tag()
    view_path(tmp_path, OTHER).unlink()

    assert len({alone, both, rewritten}) == 3
    assert client.get("/api/v1/lineage", headers=matching(both)).status_code == 200
    assert tag() == alone


def test_an_empty_list_has_an_etag_but_no_last_modified(tmp_path: Path) -> None:
    client = TestClient(create_app(atlas_data_root=tmp_path))

    empty = client.get("/api/v1/lineage")

    assert empty.json() == {"laws": []}
    assert "last-modified" not in empty.headers
    assert client.get("/api/v1/lineage", headers=matching(empty.headers["etag"])).status_code == 304


# --- Errors -----------------------------------------------------------------------------------


def test_errors_keep_their_messages_and_are_never_stored(tmp_path: Path) -> None:
    client = TestClient(create_app(atlas_data_root=tmp_path))

    missing = client.get("/api/v1/lineage/2099-0001-COD", headers=matching("*"))
    assert missing.status_code == 404
    assert missing.json()["detail"] == (
        "No lineage view for 2099-0001-COD: run `make lineage LAW=...` for that law first"
    )
    assert missing.headers["cache-control"] == "no-store"
    assert "etag" not in missing.headers

    view_path(tmp_path).parent.mkdir(parents=True)
    view_path(tmp_path).write_text("{}")
    for url in (f"/api/v1/lineage/{SLUG}", "/api/v1/lineage"):
        broken = client.get(url)
        assert broken.status_code == 500, url
        assert broken.json()["detail"].startswith("The lineage view at "), url
        assert broken.headers["cache-control"] == "no-store", url
        assert "etag" not in broken.headers, url


def test_a_view_removed_between_stat_and_read_is_a_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = world(tmp_path)

    def removed(_data_root: Path, _slug: str) -> None:
        return None

    monkeypatch.setattr(lineage, "read_lineage_view", removed)

    gone = client.get(f"/api/v1/lineage/{SLUG}")

    assert gone.status_code == 404
    assert gone.headers["cache-control"] == "no-store"


# --- The service -----------------------------------------------------------------------------


def test_view_stats_follow_the_list_order_without_reading(tmp_path: Path) -> None:
    _, view = world(tmp_path)
    add_other(tmp_path, view, LATER_MTIME_NS)
    view_path(tmp_path).chmod(0)  # unreadable: a stat must not need to read

    try:
        stats = lineage_views.view_stats(tmp_path)
        one = lineage_views.view_stat(tmp_path, SLUG)
    finally:
        view_path(tmp_path).chmod(0o644)

    assert [stat.slug for stat in stats] == [SLUG, OTHER]
    assert [stat.mtime_ns for stat in stats] == [MTIME_NS, LATER_MTIME_NS]
    assert one == stats[0]
    assert stats[0].size == view_path(tmp_path).stat().st_size
    assert lineage_views.view_stat(tmp_path, "2099-0001-COD") is None
