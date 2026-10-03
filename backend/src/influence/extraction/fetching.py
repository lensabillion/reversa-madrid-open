"""One way to reach the network: declared identity, rate limit, cache first, raw on disk.

Rate limit and identity are not politeness. An IP block at 14:00 ends the day, so every
request carries a contact address and no two requests leave closer than the interval.
"""

import http.client
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.client import HTTPResponse
from pathlib import Path
from typing import BinaryIO, Protocol

from influence.extraction.cache import CachedResponse, HttpCache, ResponseMetadata, request_key
from influence.extraction.files import open_atomic

# Identity and contact, so a provider can reach the team instead of blocking the address.
USER_AGENT = (
    "InfluenceAtlas/0.1 (Madrid Open 2026 research prototype; "
    "contact: estrellatrabancapineda@gmail.com)"
)
# Two requests a second. Cellar throttles a tight loop and Have Your Say is not faster.
MIN_INTERVAL_SECONDS = 0.5
DEFAULT_TIMEOUT_SECONDS = 60.0
ALLOWED_SCHEMES = ("https://", "http://")
# 300 Multiple Choices carries a body listing the alternatives (Cellar answers a proposal's
# CELEX this way). urllib raises for it, so the fetcher hands the body back instead.
MULTIPLE_CHOICES = 300
# A streamed download is copied in pieces of this size, so memory stays flat however large
# the file (the bulk files run to about 120 MB each).
DOWNLOAD_CHUNK_BYTES = 1 << 20


class FetchError(RuntimeError):
    """A request did not produce a usable response. The status is kept when there was one."""

    def __init__(self, url: str, reason: str, status: int | None = None) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason
        self.status = status


@dataclass(frozen=True)
class RawResponse:
    status: int
    content_type: str | None
    body: bytes


@dataclass(frozen=True)
class ResponseHead:
    """What a streamed response says about itself; its body went to the caller's file."""

    status: int
    content_type: str | None


class Fetcher(Protocol):
    """One GET. Headers are optional so a source that needs none keeps a one-argument call."""

    def __call__(self, url: str, headers: Mapping[str, str] | None = None) -> RawResponse: ...


class Streamer(Protocol):
    """One GET whose body is written to `sink` piece by piece, never held whole in memory."""

    def __call__(self, url: str, sink: BinaryIO) -> ResponseHead: ...


@dataclass
class RateLimiter:
    """Spaces calls by at least `interval`, using injected time so tests never sleep."""

    interval: float = MIN_INTERVAL_SECONDS
    monotonic: Callable[[], float] = field(default_factory=lambda: time.monotonic)
    sleep: Callable[[float], None] = field(default_factory=lambda: time.sleep)
    _last: float | None = None

    def wait(self) -> None:
        now = self.monotonic()
        if self._last is not None:
            remaining = self.interval - (now - self._last)
            if remaining > 0:
                self.sleep(remaining)
                now = self.monotonic()
        self._last = now


@dataclass(frozen=True)
class UrllibFetcher:
    """The standard library is enough for GET requests; no HTTP dependency is added."""

    timeout: float = DEFAULT_TIMEOUT_SECONDS

    def __call__(self, url: str, headers: Mapping[str, str] | None = None) -> RawResponse:
        request = _request(url, headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                return _read(response)
        except urllib.error.HTTPError as error:
            if error.code == MULTIPLE_CHOICES:
                with error:
                    return RawResponse(error.code, error.headers.get("Content-Type"), error.read())
            raise FetchError(url, f"HTTP {error.code}", error.code) from error
        except (urllib.error.URLError, OSError) as error:
            raise FetchError(url, f"No response: {error}") from error

    def stream(self, url: str, sink: BinaryIO) -> ResponseHead:
        """Copy the body to `sink` in chunks of `DOWNLOAD_CHUNK_BYTES`.

        `HTTPResponse.read(n)` returns `b""` when the connection drops before the declared
        Content-Length, instead of raising (CPython's `http/client.py` says so), so the
        bytes are counted here: a short body is an error, never a smaller file.
        """
        request = _request(url, None)
        try:
            response: HTTPResponse = urllib.request.urlopen(request, timeout=self.timeout)  # noqa: S310
        except urllib.error.HTTPError as error:
            with error:
                raise FetchError(url, f"HTTP {error.code}", error.code) from error
        except (urllib.error.URLError, OSError) as error:
            raise FetchError(url, f"No response: {error}") from error
        received = 0
        with response:
            declared = response.length
            while True:
                try:
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                except (OSError, http.client.HTTPException) as error:
                    raise FetchError(
                        url, f"Body cut off after {received} bytes: {error}"
                    ) from error
                if not chunk:
                    break
                sink.write(chunk)
                received += len(chunk)
            head = ResponseHead(response.status, response.headers.get("Content-Type"))
        if declared is not None and received != declared:
            raise FetchError(url, f"Body cut off after {received} of {declared} bytes")
        return head


def _request(url: str, headers: Mapping[str, str] | None) -> urllib.request.Request:
    if not url.startswith(ALLOWED_SCHEMES):
        raise FetchError(url, "Only http and https URLs are fetched")
    # The identity goes last so no caller header can replace the contact address.
    sent = {**(headers or {}), "User-Agent": USER_AGENT}
    # The scheme guard above is what S310 asks for; Ruff cannot see it from here.
    return urllib.request.Request(url, headers=sent)  # noqa: S310


def _read(response: HTTPResponse) -> RawResponse:
    return RawResponse(response.status, response.headers.get("Content-Type"), response.read())


@dataclass(frozen=True)
class CachedFetcher:
    """Cache-first reads and raw-to-disk writes, the two rules every source obeys."""

    cache: HttpCache
    fetcher: Fetcher = field(default_factory=UrllibFetcher)
    limiter: RateLimiter = field(default_factory=RateLimiter)
    clock: Callable[[], datetime] = field(default_factory=lambda: _utc_now)
    streamer: Streamer = field(default_factory=lambda: UrllibFetcher().stream)

    def get(
        self,
        url: str,
        *,
        refresh: bool = False,
        headers: Mapping[str, str] | None = None,
        accept_status: Collection[int] = (),
    ) -> CachedResponse:
        """Return the cached entry when there is one, otherwise fetch, store and return.

        A non-2xx response is an error, not an entry: caching a 503 would hide a source
        that came back later in the day. `accept_status` names the exceptions a caller
        can use (Cellar's 300 list of streams); an entry stored under such a status is
        invisible to a caller that did not ask for it.
        """
        key = request_key("GET", url, _header_bytes(headers))
        if not refresh:
            cached = self.cache.load(key)
            if cached is not None and _usable(cached.metadata.status, accept_status):
                return cached
        self.limiter.wait()
        # A fetcher written before headers existed takes one argument; it still serves
        # every request that sends none.
        response = self.fetcher(url) if headers is None else self.fetcher(url, headers)
        if not _usable(response.status, accept_status):
            raise FetchError(url, f"HTTP {response.status}", response.status)
        metadata = ResponseMetadata(
            key=key,
            method="GET",
            url=url,
            status=response.status,
            content_type=response.content_type,
            fetched_at=self.clock(),
            byte_count=len(response.body),
        )
        return self.cache.store(metadata, response.body)

    def download(self, url: str, destination: Path) -> ResponseMetadata:
        """Stream one bulk file to `destination`, which only a whole 2xx body replaces.

        Bulk files (a Parltrack dump, the register export) bypass the cache: holding one
        in memory and keeping a second copy under `cache/` buys nothing, because the file
        itself is the stored copy and the caller decides when to fetch it again. A
        failure, a non-2xx answer or a short body leaves `destination` as it was.
        """
        self.limiter.wait()
        fetched_at = self.clock()
        with open_atomic(destination) as sink:
            head = self.streamer(url, sink)
            if not _usable(head.status, ()):
                raise FetchError(url, f"HTTP {head.status}", head.status)
            byte_count = sink.tell()
        return ResponseMetadata(
            key=request_key("GET", url, b""),
            method="GET",
            url=url,
            status=head.status,
            content_type=head.content_type,
            fetched_at=fetched_at,
            byte_count=byte_count,
        )


def _usable(status: int, accept_status: Collection[int]) -> bool:
    return 200 <= status < 300 or status in accept_status


def _header_bytes(headers: Mapping[str, str] | None) -> bytes:
    """The part of the cache key that request headers add; empty when none are sent.

    Content negotiation makes one URL answer with different documents, so two Accept
    headers must not share an entry. No headers yields the empty body the key had before
    headers existed, which keeps every entry already on disk valid. Names are lowercased
    and sorted because HTTP header names are case-insensitive and unordered.
    """
    if headers is None:
        return b""
    lines = sorted(f"{name.lower()}: {value}" for name, value in headers.items())
    return "\n".join(["headers", *lines]).encode("utf-8")


def _utc_now() -> datetime:
    return datetime.now(UTC)
