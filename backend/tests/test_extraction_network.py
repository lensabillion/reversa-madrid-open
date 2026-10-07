"""Fetching, probing and raw storage: cache-first reads, rate limiting, fail-soft probes."""

import http.client
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import override

import pytest
from extraction_fixtures import FETCHED_AT, FakeUrlResponse, RecordingFetcher

from influence.extraction import fetching
from influence.extraction.cache import HttpCache, request_key
from influence.extraction.fetching import (
    USER_AGENT,
    CachedFetcher,
    FetchError,
    RateLimiter,
    RawResponse,
    ResponseHead,
    UrllibFetcher,
)

DUMP_URL = "https://parltrack.org/dumps/ep_meps.json.zst"


def fetcher_for(
    tmp_path: Path, responses: dict[str, RawResponse]
) -> tuple[CachedFetcher, RecordingFetcher]:
    recording = RecordingFetcher(responses, [])
    return (
        CachedFetcher(
            cache=HttpCache(tmp_path / "cache"),
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
    assert "contact: https://github.com/lensabillion/reversa-madrid-open" in USER_AGENT
    assert "@" not in USER_AGENT


def test_urllib_fetcher_sends_caller_headers_but_never_lets_them_replace_the_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> FakeUrlResponse:
        seen.append(request)
        return FakeUrlResponse(200, b"<html/>", "application/xhtml+xml")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    UrllibFetcher()(
        "http://publications.europa.eu/resource/celex/32024R1689",
        {"Accept": "application/xhtml+xml", "Accept-Language": "eng", "User-Agent": "anonymous"},
    )
    assert seen[0].get_header("Accept") == "application/xhtml+xml"
    assert seen[0].get_header("Accept-language") == "eng"
    assert seen[0].get_header("User-agent") == USER_AGENT


def test_urllib_fetcher_returns_the_body_of_a_multiple_choices_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "http://publications.europa.eu/resource/celex/52021PC0206"
    answer_headers = Message()
    answer_headers["Content-Type"] = "application/xhtml+xml"
    choices = urllib.error.HTTPError(
        url, 300, "Multiple Choices", answer_headers, BytesIO(b"<ul>streams</ul>")
    )

    def choose(request: urllib.request.Request, timeout: float) -> FakeUrlResponse:
        raise choices

    monkeypatch.setattr(urllib.request, "urlopen", choose)
    response = UrllibFetcher()(url)
    assert response == RawResponse(300, "application/xhtml+xml", b"<ul>streams</ul>")
    assert choices.closed


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


def test_streaming_copies_the_body_in_fixed_chunks_and_sends_the_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[urllib.request.Request] = []
    answer = FakeUrlResponse(200, b"0123456789", "application/zstd", length=10)

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> FakeUrlResponse:
        seen.append(request)
        return answer

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetching, "DOWNLOAD_CHUNK_BYTES", 4)
    sink = BytesIO()

    head = UrllibFetcher().stream(DUMP_URL, sink)

    assert head == ResponseHead(200, "application/zstd")
    assert sink.getvalue() == b"0123456789"
    # Never one read of the whole body: memory stays at one chunk whatever the file size.
    assert answer.reads == [4, 4, 4, 4]
    assert seen[0].get_header("User-agent") == USER_AGENT


def test_streaming_refuses_a_body_shorter_than_its_declared_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # http.client's read(n) returns b"" when the connection drops early instead of raising.
    def cut_off(request: urllib.request.Request, timeout: float) -> FakeUrlResponse:
        return FakeUrlResponse(200, b"half", length=10)

    monkeypatch.setattr(urllib.request, "urlopen", cut_off)
    with pytest.raises(FetchError, match="cut off after 4 of 10 bytes"):
        UrllibFetcher().stream(DUMP_URL, BytesIO())


def test_streaming_reports_a_dropped_connection_a_refusal_and_a_dead_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Dropped(FakeUrlResponse):
        @override
        def read(self, amt: int | None = None) -> bytes:
            raise http.client.IncompleteRead(b"par", 10)

    def drop(request: urllib.request.Request, timeout: float) -> FakeUrlResponse:
        return Dropped(200, b"")

    monkeypatch.setattr(urllib.request, "urlopen", drop)
    with pytest.raises(FetchError, match="cut off after 0 bytes"):
        UrllibFetcher().stream(DUMP_URL, BytesIO())

    refusal = urllib.error.HTTPError(DUMP_URL, 404, "Not Found", Message(), BytesIO(b""))

    def refuse(request: urllib.request.Request, timeout: float) -> FakeUrlResponse:
        raise refusal

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(FetchError) as refused:
        UrllibFetcher().stream(DUMP_URL, BytesIO())
    assert refused.value.status == 404
    assert refusal.closed

    def unreachable(request: urllib.request.Request, timeout: float) -> FakeUrlResponse:
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(urllib.request, "urlopen", unreachable)
    with pytest.raises(FetchError, match="No response") as failed:
        UrllibFetcher().stream(DUMP_URL, BytesIO())
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


def test_request_headers_reach_the_fetcher_and_separate_cache_entries(tmp_path: Path) -> None:
    url = "http://publications.europa.eu/resource/celex/32024R1689"
    fetcher, recording = fetcher_for(tmp_path, {url: RawResponse(200, "text/html", b"page")})
    xhtml = {"Accept": "application/xhtml+xml", "Accept-Language": "eng"}
    plain = fetcher.get(url)
    negotiated = fetcher.get(url, headers=xhtml)
    assert recording.headers == [None, xhtml]
    assert negotiated.metadata.key != plain.metadata.key
    # Header names are case-insensitive and unordered, so neither changes the entry.
    fetcher.get(url, headers={"accept-language": "eng", "ACCEPT": "application/xhtml+xml"})
    assert len(recording.calls) == 2
    fetcher.get(url, headers={"Accept": "application/rdf+xml", "Accept-Language": "eng"})
    assert len(recording.calls) == 3


def test_a_request_without_headers_keeps_the_cache_key_it_had_before_headers_existed(
    tmp_path: Path,
) -> None:
    url = "https://transparency-register.europa.eu/"
    fetcher, _ = fetcher_for(tmp_path, {url: RawResponse(200, "text/html", b"page")})
    assert fetcher.get(url).metadata.key == request_key("GET", url, b"")
    assert fetcher.get(url, headers={}).metadata.key != request_key("GET", url, b"")


def test_a_fetcher_written_before_headers_existed_still_serves_plain_requests(
    tmp_path: Path,
) -> None:
    def one_argument(url: str) -> RawResponse:
        return RawResponse(200, None, url.encode())

    fetcher = CachedFetcher(
        cache=HttpCache(tmp_path),
        fetcher=one_argument,  # pyright: ignore[reportArgumentType]
        limiter=RateLimiter(monotonic=lambda: 0.0, sleep=lambda _: None),
        clock=lambda: FETCHED_AT,
    )
    assert fetcher.get("https://a.eu/").body == b"https://a.eu/"


def test_a_multiple_choices_answer_is_usable_only_by_a_caller_that_asks_for_it(
    tmp_path: Path,
) -> None:
    url = "http://publications.europa.eu/resource/celex/52021PC0206"
    fetcher, recording = fetcher_for(tmp_path, {url: RawResponse(300, "text/html", b"streams")})
    with pytest.raises(FetchError, match="HTTP 300") as refused:
        fetcher.get(url)
    assert refused.value.status == 300
    listed = fetcher.get(url, accept_status=(300,))
    assert (listed.metadata.status, listed.body) == (300, b"streams")
    assert fetcher.get(url, accept_status=(300,)).body == b"streams"
    assert recording.calls == [url, url]
    # The stored 300 is not an answer for a caller that expects a document.
    with pytest.raises(FetchError, match="HTTP 300"):
        fetcher.get(url)
    assert recording.calls == [url, url, url]


def test_cached_fetcher_defaults_to_the_standard_library_and_a_real_clock(
    tmp_path: Path,
) -> None:
    fetcher = CachedFetcher(cache=HttpCache(tmp_path))
    assert isinstance(fetcher.fetcher, UrllibFetcher)
    assert fetcher.clock().tzinfo == UTC
    assert fetcher.clock() > datetime(2026, 1, 1, tzinfo=UTC)
