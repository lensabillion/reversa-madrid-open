"""On-disk contracts: atomic writes, path layout, table round trips, cache, manifest."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from extraction_fixtures import FETCHED_AT, PROVENANCE, make_actor
from pydantic import ValidationError

from influence.extraction.cache import (
    CacheError,
    HttpCache,
    ResponseMetadata,
    request_key,
)
from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import DataLayout, LayoutError, procedure_slug
from influence.extraction.manifest import (
    DocumentReference,
    LawManifest,
    ManifestError,
    SourceAvailability,
    read_manifest,
    write_manifest,
)
from influence.extraction.tables import ActorRow, AskRow, TableError, read_table, write_table


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


def test_layout_separates_global_sources_per_law_directories_and_parsed_tables(
    tmp_path: Path,
) -> None:
    layout = DataLayout(tmp_path)
    assert layout.raw == tmp_path / "raw"
    assert layout.parsed == tmp_path / "parsed"
    assert layout.cache == tmp_path / "cache"
    assert layout.global_source("registry") == tmp_path / "raw" / "registry"
    assert layout.law("2021/0106(COD)") == tmp_path / "raw" / "laws" / "2021-0106-COD"
    assert layout.manifest("2021/0106(COD)").name == "manifest.json"
    assert layout.law_source("2021/0106(COD)", "hys").name == "hys"
    assert layout.table("asks") == tmp_path / "parsed" / "asks.jsonl"


@pytest.mark.parametrize(
    ("call", "argument"),
    [("global_source", "lobbyfacts"), ("table", "winners")],
)
def test_layout_rejects_names_outside_the_known_sets(
    tmp_path: Path, call: str, argument: str
) -> None:
    method = getattr(DataLayout(tmp_path), call)
    with pytest.raises(LayoutError):
        method(argument)


@pytest.mark.parametrize("name", ["", "a/b", "a\\b"])
def test_layout_rejects_per_law_source_names_that_escape_the_law_directory(
    tmp_path: Path, name: str
) -> None:
    with pytest.raises(LayoutError, match="Unusable per-law source name"):
        DataLayout(tmp_path).law_source("2021/0106(COD)", name)


def test_table_round_trip_preserves_text_with_delimiters_and_skips_blank_lines(
    tmp_path: Path,
) -> None:
    path = tmp_path / "asks.jsonl"
    ask = AskRow(
        ask_id="24212003-1-p4",
        law_id="2021/0106(COD)",
        actor_raw_name='Example, "Tech" GmbH\tBerlin',
        actor_id=None,
        match_method="unresolved",
        submitted_at=None,
        channel="hys_attachment",
        text="Article 6(2)(a) should read: 'high-risk', not high risk;\nwith a newline",
        page=4,
        offset=120,
        **PROVENANCE,
    )
    assert write_table(path, [ask]) == 1
    path.write_text(f"{path.read_text(encoding='utf-8')}\n   \n", encoding="utf-8")
    assert list(read_table(path, AskRow)) == [ask]


def test_read_table_names_the_file_when_it_is_absent_and_the_line_when_it_is_invalid(
    tmp_path: Path,
) -> None:
    with pytest.raises(TableError, match=r"Cannot read missing\.jsonl"):
        list(read_table(tmp_path / "missing.jsonl", ActorRow))
    path = tmp_path / "actors.jsonl"
    write_table(path, [make_actor("1", "Example Association")])
    path.write_text(f'{path.read_text(encoding="utf-8")}{{"actor_id": "2"}}\n', encoding="utf-8")
    with pytest.raises(TableError, match=r"actors\.jsonl line 2 is invalid"):
        list(read_table(path, ActorRow))


def test_rows_reject_an_undeclared_field_so_a_parser_cannot_invent_one() -> None:
    with pytest.raises(ValidationError):
        ActorRow(
            actor_id="1",
            name="Example",
            acronym=None,
            category="ngo",
            country=None,
            budget_eur=None,
            budget_raw=None,
            win_rate=0.5,  # pyright: ignore[reportCallIssue]
            **PROVENANCE,
        )


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


def test_availability_names_every_source_it_has_not_confirmed() -> None:
    assert SourceAvailability(oeil=True, hys=True).missing() == (
        "eurlex_proposal",
        "eurlex_final",
        "amendments",
    )
    assert (
        SourceAvailability(
            oeil=True, eurlex_proposal=True, eurlex_final=True, hys=True, amendments=True
        ).missing()
        == ()
    )


def test_manifest_round_trip_keeps_every_derived_identifier(tmp_path: Path) -> None:
    manifest = LawManifest(
        procedure_id="2021/0106(COD)",
        title="Artificial Intelligence Act",
        celex_proposal="52021PC0206",
        celex_final="32024R1689",
        lead_committee="IMCO-LIBE",
        rapporteurs=("Example MEP",),
        hys_publication_id=24212003,
        documents=(DocumentReference(type="amendments", url="https://oeil.europa.eu/doc"),),
        available=SourceAvailability(oeil=True, hys=True, amendments=True),
        resolved_at=datetime(2026, 10, 3, 9, 45, tzinfo=UTC),
    )
    path = tmp_path / "manifest.json"
    write_manifest(path, manifest)
    assert read_manifest(path) == manifest


def test_manifest_read_reports_an_absent_or_invalid_file(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    with pytest.raises(ManifestError, match="Cannot read manifest"):
        read_manifest(path)
    path.write_text('{"title": "no procedure id"}', encoding="utf-8")
    with pytest.raises(ManifestError, match="is invalid"):
        read_manifest(path)
