"""Atomic file writes, so an interrupted run never leaves a half-written output."""

import os
from pathlib import Path


def write_bytes_atomic(path: Path, content: bytes) -> None:
    """Write to a sibling temporary file, flush to disk, then rename over the target.

    The rename is atomic on POSIX and on Windows (os.replace), so a reader sees either
    the previous complete file or the new complete file, never a truncated one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
