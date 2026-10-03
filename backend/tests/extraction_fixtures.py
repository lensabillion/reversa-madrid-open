"""Row and response builders shared by the extraction tests."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import Message
from typing import TypedDict

from influence.extraction.fetching import RawResponse
from influence.extraction.tables import ActorRow

FETCHED_AT = datetime(2026, 10, 3, 9, 30, tzinfo=UTC)


class ProvenanceFields(TypedDict):
    """The three provenance fields every row carries, typed so `**` unpacking checks."""

    source_url: str
    fetched_at: datetime
    extraction_method: str


PROVENANCE: ProvenanceFields = {
    "source_url": "https://transparency-register.europa.eu/",
    "fetched_at": FETCHED_AT,
    "extraction_method": "test",
}


def make_actor(actor_id: str, name: str, acronym: str | None = None) -> ActorRow:
    return ActorRow(
        actor_id=actor_id,
        name=name,
        acronym=acronym,
        category="trade_association",
        country="BE",
        budget_eur=None,
        budget_raw=None,
        interests=(),
        **PROVENANCE,
    )


@dataclass
class FakeUrlResponse:
    """Stands in for http.client.HTTPResponse: status, headers and a single read()."""

    status: int
    body: bytes
    content_type: str | None = None

    @property
    def headers(self) -> Message:
        message = Message()
        if self.content_type is not None:
            message["Content-Type"] = self.content_type
        return message

    def read(self) -> bytes:
        return self.body

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
