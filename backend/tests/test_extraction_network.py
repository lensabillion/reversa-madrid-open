"""Fetching, probing and raw storage: cache-first reads, rate limiting, fail-soft probes."""

import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from email.message import Message
from io import BytesIO
from pathlib import Path

import pytest
from extraction_fixtures import FETCHED_AT, FakeUrlResponse, RecordingFetcher
from pydantic import ValidationError

from influence.extraction import catalog, probe, pull
from influence.extraction.cache import HttpCache
from influence.extraction.catalog import SourceSpec
from influence.extraction.fetching import (
    USER_AGENT,
    CachedFetcher,
    FetchError,
    RateLimiter,
    RawResponse,
    UrllibFetcher,
)
from influence.extraction.layout import DataLayout, LayoutError

REGISTRY = catalog.source("A")
AMENDMENTS = catalog.source("H")
OEIL = catalog.source("E")


def fetcher_for(
    tmp_path: Path, responses: dict[str, RawResponse]
) -> tuple[CachedFetcher, RecordingFetcher]:
    recording = RecordingFetcher(responses, [])
    return (
        CachedFetcher(
            cache=HttpCache(DataLayout(tmp_path).cache),
            fetcher=recording,
            limiter=RateLimiter(monotonic=lambda: 0.0, sleep=lambda _: None),
            clock=lambda: FETCHED_AT,
        ),
        recording,
    )


def test_rate_limiter_sleeps_only_for_the_time_still_owed() -> None:
    times: Iterator[float] = iter([0.0, 0.1, 0.5, 10.0])
    slept: list[float] = []
    limiter = RateLimiter(interval=0.5, monotonic=lambda: next(times), sleep=slept.append)
    limiter.wait()
    limiter.wait()
    limiter.wait()
    assert slept == [pytest.approx(0.4)]


def test_rate_limiter_defaults_to_the_real_clock_and_two_requests_a_second() -> None:
    limiter = RateLimiter()
    assert limiter.interval == 0.5
    assert limiter.monotonic() > 0


def test_urllib_fetcher_sends_a_contact_address_and_returns_status_type_and_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> FakeUrlResponse:
        assert timeout == 5.0
        seen.append(request)
        return FakeUrlResponse(200, b"<register/>", "application/xml")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    response = UrllibFetcher(timeout=5.0)("https://transparency-register.europa.eu/")
    assert response == RawResponse(200, "application/xml", b"<register/>")
    assert seen[0].get_header("User-agent") == USER_AGENT
    assert "contact:" in USER_AGENT


def test_urllib_fetcher_refuses_a_scheme_it_was_not_asked_to_support() -> None:
    with pytest.raises(FetchError, match="Only http and https"):
        UrllibFetcher()("file:///etc/passwd")


def test_urllib_fetcher_keeps_the_status_of_a_refusal_and_reports_a_dead_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # urllib's HTTPError is a temporary-file wrapper, so an unclosed one raises during
    # garbage collection and lands as an unraisable exception in an unrelated test.
    refusal = urllib.error.HTTPError(
        "https://oeil.secure.europarl.europa.eu/", 429, "Too Many", Message(), BytesIO(b"")
    )

    def refuse(request: urllib.request.Request, timeout: float) -> FakeUrlResponse:
        raise refusal

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    try:
        with pytest.raises(FetchError) as refused:
            UrllibFetcher()("https://oeil.secure.europarl.europa.eu/")
        assert refused.value.status == 429
    finally:
        refusal.close()

    def unreachable(request: urllib.request.Request, timeout: float) -> FakeUrlResponse:
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(urllib.request, "urlopen", unreachable)
    with pytest.raises(FetchError) as failed:
        UrllibFetcher()("https://oeil.secure.europarl.europa.eu/")
    assert failed.value.status is None


def test_a_repeated_request_never_leaves_the_machine_unless_refresh_is_asked(
    tmp_path: Path,
) -> None:
    url = "https://transparency-register.europa.eu/"
    fetcher, recording = fetcher_for(tmp_path, {url: RawResponse(200, "text/html", b"page")})
    first = fetcher.get(url)
    second = fetcher.get(url)
    assert second.body == first.body == b"page"
    assert recording.calls == [url]
    fetcher.get(url, refresh=True)
    assert recording.calls == [url, url]
    assert first.metadata.fetched_at == FETCHED_AT


def test_a_server_error_is_raised_rather_than_cached(tmp_path: Path) -> None:
    url = "https://oeil.secure.europarl.europa.eu/"
    fetcher, recording = fetcher_for(tmp_path, {url: RawResponse(503, None, b"busy")})
    with pytest.raises(FetchError, match="HTTP 503"):
        fetcher.get(url)
    with pytest.raises(FetchError):
        fetcher.get(url)
    assert recording.calls == [url, url]


def test_cached_fetcher_defaults_to_the_standard_library_and_a_real_clock(
    tmp_path: Path,
) -> None:
    fetcher = CachedFetcher(cache=HttpCache(tmp_path))
    assert isinstance(fetcher.fetcher, UrllibFetcher)
    assert fetcher.clock().tzinfo == UTC
    assert fetcher.clock() > datetime(2026, 1, 1, tzinfo=UTC)


def test_probe_records_what_a_source_returned_including_a_truncated_sniff(
    tmp_path: Path,
) -> None:
    assert REGISTRY.probe_url is not None
    body = b"<register>" + b"x" * 1000
    fetcher, _ = fetcher_for(tmp_path, {REGISTRY.probe_url: RawResponse(200, "text/xml", body)})
    result = probe.probe_source(fetcher, REGISTRY)
    assert result.reachable
    assert (result.status, result.content_type, result.byte_count) == (200, "text/xml", len(body))
    assert result.sniff is not None
    assert len(result.sniff) == probe.SNIFF_CHARACTERS
    assert result.error is None


def test_probe_turns_a_refusal_into_a_recorded_result_so_the_run_continues(
    tmp_path: Path,
) -> None:
    assert OEIL.probe_url is not None
    fetcher, _ = fetcher_for(tmp_path, {OEIL.probe_url: RawResponse(500, None, b"")})
    result = probe.probe_source(fetcher, OEIL)
    assert (result.reachable, result.status, result.sniff) == (False, 500, None)
    assert result.error == "HTTP 500"


def test_probing_a_source_without_a_base_url_is_a_programming_error(tmp_path: Path) -> None:
    fetcher, _ = fetcher_for(tmp_path, {})
    with pytest.raises(ValueError, match="no probe URL"):
        probe.probe_source(fetcher, AMENDMENTS)


def test_probe_sources_skips_sources_with_no_base_url_and_names_the_unreachable(
    tmp_path: Path,
) -> None:
    specs = (REGISTRY, AMENDMENTS, OEIL)
    assert REGISTRY.probe_url is not None
    assert OEIL.probe_url is not None
    fetcher, _ = fetcher_for(
        tmp_path,
        {
            REGISTRY.probe_url: RawResponse(200, "text/html", b"page"),
            OEIL.probe_url: RawResponse(404, None, b""),
        },
    )
    report = probe.probe_sources(fetcher, specs)
    assert [result.letter for result in report.results] == ["A", "E"]
    assert [result.letter for result in report.unreachable()] == ["E"]
    path = tmp_path / "probe-report.json"
    probe.write_report(path, report)
    assert probe.ProbeReport.model_validate_json(path.read_bytes()) == report
    formatted = probe.format_report(report)
    assert "A registry [confirmed] 200 text/html, 4 bytes" in formatted
    assert "E oeil [unverified] unreachable: HTTP 404" in formatted


def test_format_report_names_a_missing_content_type_rather_than_printing_none(
    tmp_path: Path,
) -> None:
    assert REGISTRY.probe_url is not None
    fetcher, _ = fetcher_for(tmp_path, {REGISTRY.probe_url: RawResponse(200, None, b"x")})
    report = probe.probe_sources(fetcher, (REGISTRY,))
    assert "no content type" in probe.format_report(report)


def test_raw_storage_puts_the_bytes_and_their_provenance_under_the_source(
    tmp_path: Path,
) -> None:
    layout = DataLayout(tmp_path)
    url = "https://transparency-register.europa.eu/full.xml"
    fetcher, _ = fetcher_for(tmp_path, {url: RawResponse(200, "text/xml", b"<register/>")})
    stored = pull.store_raw(layout, REGISTRY, fetcher, url, name="full.xml")
    assert stored.body_path == layout.global_source("registry") / "full.xml"
    assert stored.body_path.read_bytes() == b"<register/>"
    assert stored.byte_count == 11
    assert '"url"' in stored.provenance_path.read_text(encoding="utf-8")


def test_a_per_law_source_is_stored_under_its_procedure_and_needs_one(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    url = "https://oeil.secure.europarl.europa.eu/procedure"
    fetcher, _ = fetcher_for(tmp_path, {url: RawResponse(200, "text/html", b"<html/>")})
    stored = pull.store_raw(layout, OEIL, fetcher, url, name="oeil", procedure_id="2021/0106(COD)")
    assert stored.body_path.parent == layout.law_source("2021/0106(COD)", "oeil")
    with pytest.raises(LayoutError, match="needs a procedure id"):
        pull.target_directory(layout, OEIL, None)


def test_raw_storage_refuses_a_name_that_would_escape_the_directory(tmp_path: Path) -> None:
    fetcher, recording = fetcher_for(tmp_path, {})
    with pytest.raises(LayoutError, match="Unusable raw file name"):
        pull.store_raw(DataLayout(tmp_path), REGISTRY, fetcher, "https://a.eu", name="../out")
    assert recording.calls == []


def test_the_catalog_letters_ids_and_target_tables_are_unique_and_known() -> None:
    assert len({spec.letter for spec in catalog.SOURCES}) == len(catalog.SOURCES)
    assert len({spec.source_id for spec in catalog.SOURCES}) == len(catalog.SOURCES)
    assert catalog.source("registry") is catalog.source("a")
    assert {spec.letter for spec in catalog.by_scope("global")} == {"A", "B", "C", "D"}
    assert AMENDMENTS not in catalog.probeable(catalog.SOURCES)
    with pytest.raises(catalog.UnknownSourceError):
        catalog.source("Z")


def test_a_source_cannot_declare_a_table_that_does_not_exist() -> None:
    with pytest.raises(ValidationError, match="Unknown target tables: winners"):
        SourceSpec(
            letter="Z",
            source_id="invented",
            name="Invented",
            scope="global",
            verification="unverified",
            probe_url=None,
            target_tables=("winners",),
            notes="",
        )
