"""Atomic file writes, so an interrupted run never leaves a half-written output."""

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO


@contextmanager
def open_atomic(path: Path) -> Generator[BinaryIO]:
    """A handle on a sibling temporary file that becomes `path` only if the block succeeds.

    For output too large to hold in memory, such as a streamed download. On success the
    file is flushed to disk and renamed over `path`; on any exception, including Ctrl-C,
    the temporary file is removed and `path` keeps its previous content or stays absent.
    A killed process can leave `<name>.tmp`, which no reader opens and the next write
    replaces.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        with temporary.open("wb") as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_bytes_atomic(path: Path, content: bytes) -> None:
    """Write to a sibling temporary file, flush to disk, then rename over the target.

    The rename is atomic on POSIX and on Windows (os.replace), so a reader sees either
    the previous complete file or the new complete file, never a truncated one.
    """
    with open_atomic(path) as handle:
        handle.write(content)
