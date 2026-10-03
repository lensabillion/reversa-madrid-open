"""One way to reach the network: declared identity, rate limit, cache first, raw on disk.

Rate limit and identity are not politeness. An IP block at 14:00 ends the day, so every
request carries a contact address and no two requests leave closer than the interval.
"""

import time
import urllib.error
import urllib.request
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.client import HTTPResponse
from typing import Protocol

from influence.extraction.cache import CachedResponse, HttpCache, ResponseMetadata, request_key

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


class Fetcher(Protocol):
    """One GET. Headers are optional so a source that needs none keeps a one-argument call."""

    def __call__(self, url: str, headers: Mapping[str, str] | None = None) -> RawResponse: ...


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
        if not url.startswith(ALLOWED_SCHEMES):
            raise FetchError(url, "Only http and https URLs are fetched")
        # The identity goes last so no caller header can replace the contact address.
        sent = {**(headers or {}), "User-Agent": USER_AGENT}
        # The scheme guard above is what S310 asks for; Ruff cannot see it from here.
        request = urllib.request.Request(url, headers=sent)  # noqa: S310
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


def _read(response: HTTPResponse) -> RawResponse:
    return RawResponse(response.status, response.headers.get("Content-Type"), response.read())


@dataclass(frozen=True)
class CachedFetcher:
    """Cache-first reads and raw-to-disk writes, the two rules every source obeys."""

    cache: HttpCache
    fetcher: Fetcher = field(default_factory=UrllibFetcher)
    limiter: RateLimiter = field(default_factory=RateLimiter)
    clock: Callable[[], datetime] = field(default_factory=lambda: _utc_now)

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
