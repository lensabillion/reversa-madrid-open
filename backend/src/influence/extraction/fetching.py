"""One way to reach the network: declared identity, rate limit, cache first, raw on disk.

Rate limit and identity are not politeness. An IP block at 14:00 ends the day, so every
request carries a contact address and no two requests leave closer than the interval.
"""

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.client import HTTPResponse

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


type Fetcher = Callable[[str], RawResponse]


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

    def __call__(self, url: str) -> RawResponse:
        if not url.startswith(ALLOWED_SCHEMES):
            raise FetchError(url, "Only http and https URLs are fetched")
        # The scheme guard above is what S310 asks for; Ruff cannot see it from here.
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                return _read(response)
        except urllib.error.HTTPError as error:
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

    def get(self, url: str, *, refresh: bool = False) -> CachedResponse:
        """Return the cached entry when there is one, otherwise fetch, store and return.

        A non-2xx response is an error, not an entry: caching a 503 would hide a source
        that came back later in the day.
        """
        key = request_key("GET", url, b"")
        if not refresh:
            cached = self.cache.load(key)
            if cached is not None:
                return cached
        self.limiter.wait()
        response = self.fetcher(url)
        if not 200 <= response.status < 300:
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


def _utc_now() -> datetime:
    return datetime.now(UTC)
