"""Content-addressed HTTP cache: a second identical request never leaves the machine.

The key is SHA-256 over method, URL and request body. Body and metadata are separate
files, so a parser can re-read a 40 MB response without parsing JSON around it, and an
interrupted store leaves a miss rather than a corrupt hit.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from influence.extraction.files import write_bytes_atomic


class CacheError(ValueError):
    """A cache entry exists but cannot be trusted."""


def request_key(method: str, url: str, body: bytes) -> str:
    """Hash the parts that make a request distinct, separated so no two inputs collide."""
    digest = hashlib.sha256()
    digest.update(method.upper().encode("utf-8"))
    digest.update(b"\x00")
    digest.update(url.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(body)
    return digest.hexdigest()


class ResponseMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    key: str = Field(min_length=64, max_length=64)
    method: str = Field(min_length=1)
    url: str = Field(min_length=1)
    status: int = Field(ge=100, le=599)
    content_type: str | None
    fetched_at: datetime
    byte_count: int = Field(ge=0)


@dataclass(frozen=True)
class CachedResponse:
    metadata: ResponseMetadata
    body: bytes


@dataclass(frozen=True)
class HttpCache:
    directory: Path

    def _entry(self, key: str) -> tuple[Path, Path]:
        # Two-character fan-out keeps directory listings usable at tens of thousands of
        # entries, which one flat directory does not on either filesystem we target.
        folder = self.directory / key[:2]
        return folder / f"{key}.bin", folder / f"{key}.json"

    def load(self, key: str) -> CachedResponse | None:
        """Return the entry, or None when either half is absent; raise when it is corrupt."""
        body_path, metadata_path = self._entry(key)
        try:
            raw_metadata = metadata_path.read_bytes()
            body = body_path.read_bytes()
        except OSError:
            return None
        try:
            metadata = ResponseMetadata.model_validate_json(raw_metadata)
        except ValidationError as error:
            raise CacheError(f"Cache metadata for {key} is unreadable") from error
        if metadata.byte_count != len(body):
            raise CacheError(
                f"Cache body for {key} is {len(body)} bytes, not the recorded byte_count"
            )
        return CachedResponse(metadata, body)

    def store(self, metadata: ResponseMetadata, body: bytes) -> CachedResponse:
        """Write the body first: metadata is the marker that an entry is complete."""
        if metadata.byte_count != len(body):
            raise CacheError("Metadata byte_count does not match the body it describes")
        body_path, metadata_path = self._entry(metadata.key)
        write_bytes_atomic(body_path, body)
        write_bytes_atomic(metadata_path, metadata.model_dump_json().encode("utf-8"))
        return CachedResponse(metadata, body)
