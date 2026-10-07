"""Response builders shared by the extraction tests."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import Message

from influence.extraction.fetching import RawResponse

FETCHED_AT = datetime(2026, 10, 3, 9, 30, tzinfo=UTC)


@dataclass
class FakeUrlResponse:
    """Stands in for http.client.HTTPResponse: status, headers, `length` and read().

    `length` is the declared Content-Length, which a cut-off body falls short of. `reads`
    records the size asked of every read(), None for a read of the whole rest.
    """

    status: int
    body: bytes
    content_type: str | None = None
    length: int | None = None
    reads: list[int | None] = field(default_factory=list[int | None])
    position: int = 0

    @property
    def headers(self) -> Message:
        message = Message()
        if self.content_type is not None:
            message["Content-Type"] = self.content_type
        return message

    def read(self, amt: int | None = None) -> bytes:
        self.reads.append(amt)
        end = len(self.body) if amt is None else min(len(self.body), self.position + amt)
        chunk = self.body[self.position : end]
        self.position = end
        return chunk

    def __enter__(self) -> FakeUrlResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


@dataclass
class RecordingFetcher:
    """A Fetcher that answers from a script and records the URLs it was asked for.

    `headers` records, call by call, the request headers that came with each URL (None
    when the caller sent none), so a test can assert on content negotiation.
    """

    responses: dict[str, RawResponse]
    calls: list[str]
    headers: list[Mapping[str, str] | None] = field(default_factory=list[Mapping[str, str] | None])

    def __call__(self, url: str, headers: Mapping[str, str] | None = None) -> RawResponse:
        self.calls.append(url)
        self.headers.append(headers)
        return self.responses[url]
