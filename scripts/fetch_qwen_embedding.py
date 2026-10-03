"""
Download the Qwen3-Embedding-0.6B files the meaning signal runs on, and verify them.

The model is Qwen's open embedding model (Apache-2.0 on its own model card,
https://huggingface.co/Qwen/Qwen3-Embedding-0.6B). The files are the community ONNX export
`onnx-community/Qwen3-Embedding-0.6B-ONNX`, which `onnxruntime` runs without PyTorch:
the 8-bit weights (`onnx/model_int8.onnx`, 614 MB), the tokenizer and the model config. They
go under `data/models/qwen3-embedding-0.6b/`, which is never committed, so this script is how
anyone reproduces them.

The download is pinned to one Hugging Face commit, and every file is checked against the
SHA-256 digest recorded here. A file that does not match is deleted and the script fails, so a
moved branch or a replaced weight file cannot change what the evaluation measures. A file that
already matches is left alone and nothing is fetched.

Run through `make fetch-qwen-embedding`.
"""

import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DESTINATION = REPO_ROOT / "data" / "models" / "qwen3-embedding-0.6b"
REVISION = "c25a394dd583836952667c12f008335071b3f43d"
BASE_URL = f"https://huggingface.co/onnx-community/Qwen3-Embedding-0.6B-ONNX/resolve/{REVISION}"
# Path in the repository (also the path under the destination) and its SHA-256. The weight and
# tokenizer digests are the Git LFS object ids Hugging Face publishes for this revision.
SHA256 = {
    "onnx/model_int8.onnx": "6d0ea863f78b4a84afa3c7fcba1ec341572b5e28121aef77b7092b1dfdf679c7",
    "tokenizer.json": "def76fb086971c7867b829c23a26261e38d9d74e02139253b38aeb9df8b4b50a",
    "config.json": "66a10929782f3c9a3cd5dec90e2a95c60e05736134a63cd54479eeae80bed175",
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
    print(f"Qwen3-Embedding-0.6B (ONNX int8) at revision {REVISION[:7]} is in {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
