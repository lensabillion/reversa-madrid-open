"""
Download the Qwen3-Reranker-0.6B files the meaning judge runs on, and verify them.

The reranker is Qwen's open yes/no relevance model (Apache-2.0, model card
https://huggingface.co/Qwen/Qwen3-Reranker-0.6B). The files are the community ONNX export of its
sequence-classification conversion, `shawnw3i/Qwen3-Reranker-0.6B-seq-cls-ONNX`, which maps a
(instruction, query, document) text to one score through `onnxruntime`, with no text generation:
the weights (`model.onnx`, 1.2 GB, 16-bit floats) and the tokenizer. They go under
`data/models/qwen3-reranker-0.6b/`, which is never committed, so this script is how anyone
reproduces them.

The download is pinned to one Hugging Face commit, and every file is checked against the
SHA-256 digest recorded here (the Git LFS object ids Hugging Face publishes for this revision).
A file that does not match is deleted and the script fails; a file that already matches is left
alone and nothing is fetched.

Run through `make fetch-qwen-reranker`.
"""

import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DESTINATION = REPO_ROOT / "data" / "models" / "qwen3-reranker-0.6b"
REVISION = "e5d273d8d9fbbc0dc5021008e0242d3cd85bb60d"
BASE_URL = f"https://huggingface.co/shawnw3i/Qwen3-Reranker-0.6B-seq-cls-ONNX/resolve/{REVISION}"
SHA256 = {
    "model.onnx": "bd3ee3865c63d1bec518d0785ff551f7c0b78af0d4bf4855653a0c765a2a1292",
    "tokenizer.json": "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
}
TIMEOUT_SECONDS = 120
CHUNK_BYTES = 1 << 20


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def fetch(name: str, destination: Path) -> str:
    """Make `destination/name` hold the pinned file; return what was done."""
    target = destination / name
    if target.is_file() and digest(target) == SHA256[name]:
        return "present"
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(f".{target.name}.download")
    try:
        with (
            urllib.request.urlopen(f"{BASE_URL}/{name}", timeout=TIMEOUT_SECONDS) as response,  # noqa: S310
            staged.open("wb") as sink,
        ):
            shutil.copyfileobj(response, sink, CHUNK_BYTES)
        if digest(staged) != SHA256[name]:
            raise SystemExit(f"{name}: downloaded file does not match its pinned SHA-256")
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)
    return "downloaded"


def main(argv: list[str]) -> int:
    destination = Path(argv[0]) if argv else DEFAULT_DESTINATION
    for name in SHA256:
        print(f"{name}: {fetch(name, destination)}")
    print(f"Qwen3-Reranker-0.6B (ONNX seq-cls) at revision {REVISION[:7]} is in {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
