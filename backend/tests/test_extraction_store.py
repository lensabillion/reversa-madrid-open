"""On-disk contracts: atomic writes, path layout and the HTTP cache."""

from pathlib import Path

import pytest
from extraction_fixtures import FETCHED_AT

from influence.extraction.cache import (
    CacheError,
    HttpCache,
    ResponseMetadata,
    request_key,
)
from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import LayoutError, procedure_slug


def metadata(key: str, body: bytes, *, byte_count: int | None = None) -> ResponseMetadata:
    return ResponseMetadata(
        key=key,
        method="GET",
        url="https://example.europa.eu/dump.xml",
        status=200,
        content_type="application/xml",
        fetched_at=FETCHED_AT,
        byte_count=len(body) if byte_count is None else byte_count,
    )


def test_atomic_write_creates_parents_replaces_content_and_leaves_no_temporary(
    tmp_path: Path,
) -> None:
    target = tmp_path / "raw" / "registry" / "dump.xml"
    write_bytes_atomic(target, b"first")
    write_bytes_atomic(target, b"second")
    assert target.read_bytes() == b"second"
    assert sorted(path.name for path in target.parent.iterdir()) == ["dump.xml"]


@pytest.mark.parametrize(
    ("procedure_id", "expected"),
    [("2021/0106(COD)", "2021-0106-COD"), ("  2016/0280(COD) ", "2016-0280-COD")],
)
def test_procedure_slug_keeps_only_path_safe_characters(procedure_id: str, expected: str) -> None:
    assert procedure_slug(procedure_id) == expected


def test_procedure_slug_rejects_an_id_with_nothing_to_keep() -> None:
    with pytest.raises(LayoutError, match="no usable characters"):
        procedure_slug("///")


def test_request_key_separates_its_parts_so_different_requests_cannot_collide() -> None:
    assert request_key("get", "https://a.eu/x", b"") == request_key("GET", "https://a.eu/x", b"")
    assert request_key("GET", "https://a.eu/x", b"y") != request_key("GET", "https://a.eu/xy", b"")


def test_cache_stores_then_returns_the_same_bytes(tmp_path: Path) -> None:
    cache = HttpCache(tmp_path)
    key = request_key("GET", "https://example.europa.eu/dump.xml", b"")
    stored = cache.store(metadata(key, b"<register/>"), b"<register/>")
    loaded = cache.load(key)
    assert loaded is not None
    assert loaded.body == b"<register/>"
    assert loaded.metadata == stored.metadata


def test_cache_reports_a_miss_when_either_half_is_missing(tmp_path: Path) -> None:
    cache = HttpCache(tmp_path)
    key = request_key("GET", "https://example.europa.eu/dump.xml", b"")
    assert cache.load(key) is None
    cache.store(metadata(key, b"body"), b"body")
    (tmp_path / key[:2] / f"{key}.bin").unlink()
    assert cache.load(key) is None


def test_cache_refuses_an_entry_whose_metadata_or_size_cannot_be_trusted(tmp_path: Path) -> None:
    cache = HttpCache(tmp_path)
    key = request_key("GET", "https://example.europa.eu/dump.xml", b"")
    cache.store(metadata(key, b"body"), b"body")
    (tmp_path / key[:2] / f"{key}.json").write_text("not json", encoding="utf-8")
    with pytest.raises(CacheError, match="unreadable"):
        cache.load(key)
    cache.store(metadata(key, b"body"), b"body")
    (tmp_path / key[:2] / f"{key}.bin").write_bytes(b"longer body")
    with pytest.raises(CacheError, match="recorded byte_count"):
        cache.load(key)
    with pytest.raises(CacheError, match="does not match the body"):
        cache.store(metadata(key, b"body", byte_count=99), b"body")


def test_default_data_root_uses_the_environment_or_repository_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from influence.extraction import layout

    monkeypatch.setenv("INFLUENCE_DATA_ROOT", str(tmp_path))
    assert layout.default_data_root() == tmp_path
    monkeypatch.delenv("INFLUENCE_DATA_ROOT")
    assert layout.default_data_root() == Path(layout.__file__).resolve().parents[4] / "data"
