"""Stable input identities and atomic model artifacts shared by the offline scripts."""

import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def text_key(role: str, text: str) -> str:
    """Role belongs in identity because retrieval models encode queries differently."""
    return hashlib.sha256(f"{role}\0{text}".encode()).hexdigest()


def write_json(path: Path, value: object) -> None:
    """Readers see only a completed artifact, even if inference or serialization fails."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(value, handle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)
