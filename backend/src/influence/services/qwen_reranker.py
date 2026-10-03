"""Qwen3-Reranker-0.6B on CPU through ONNX Runtime: prompts in, one yes/no log-odds each out.

The model is Qwen's yes/no relevance model in its sequence-classification form: it reads the
whole prompt (`services/judge.py` builds it) and its single output is the log-odds that the answer
is "yes". It writes no text, so a score is deterministic and costs one forward pass.

Batches are padded on the left, the way the model card does it; the usual case is one prompt per
call (`judge.BATCH_SIZE`), where there is no padding at all. Measured speed is in the PR that
added this module.

Only `load_reranker` imports the optional runtime (the `models` dependency group). Everything else
takes the session, the tokenizer and the array builder as arguments, so it is tested with fakes.
Files come from `make fetch-qwen-reranker`.
"""

import importlib
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, cast

from influence.services.qwen_onnx import QwenError

MODEL_ID = "qwen3-reranker-0.6b-seq-cls-onnx-fp16@e5d273d"
WEIGHTS = Path("model.onnx")
TOKENIZER = Path("tokenizer.json")
END_OF_TEXT = "<|endoftext|>"
# A judge prompt is a few hundred tokens; this only stops a runaway one reaching the model.
MAX_TOKENS = 4096


class _Encoding(Protocol):
    @property
    def ids(self) -> Sequence[int]: ...


class Tokenizer(Protocol):
    def encode_batch(
        self, inputs: list[str], *, add_special_tokens: bool
    ) -> Sequence[_Encoding]: ...


class Session(Protocol):
    def run(self, output_names: None, input_feed: dict[str, object]) -> Sequence[object]: ...


class IntArrays(Protocol):
    def ints(self, rows: list[list[int]]) -> object: ...


class QwenReranker:
    """Callable `ScoreFunction`: `reranker(prompts)` returns one log-odds of "yes" each."""

    def __init__(
        self, session: Session, tokenizer: Tokenizer, arrays: IntArrays, pad_id: int
    ) -> None:
        self._session = session
        self._tokenizer = tokenizer
        self._arrays = arrays
        self._pad_id = pad_id

    def __call__(self, prompts: Sequence[str]) -> list[float]:
        if not prompts:
            return []
        encodings = self._tokenizer.encode_batch(list(prompts), add_special_tokens=False)
        rows = [list(encoding.ids) for encoding in encodings]
        width = max(len(row) for row in rows)
        if width > MAX_TOKENS:
            raise QwenError(f"A prompt of {width} tokens is longer than the {MAX_TOKENS} allowed")
        ids = [[self._pad_id] * (width - len(row)) + row for row in rows]
        mask = [[0] * (width - len(row)) + [1] * len(row) for row in rows]
        feed: dict[str, object] = {
            "input_ids": self._arrays.ints(ids),
            "attention_mask": self._arrays.ints(mask),
        }
        logits = cast("Sequence[Sequence[float]]", self._session.run(None, feed)[0])
        return [float(logits[row][0]) for row in range(len(rows))]


def load_reranker(directory: Path) -> QwenReranker:  # pragma: no cover
    """Open the reranker in `directory` (see `scripts/fetch_qwen_reranker.py`) on the CPU.

    The only function that imports the optional `models` group; excluded from coverage because
    the default install does not have it. The logic it hands the runtime to is tested.
    """
    try:
        onnxruntime = importlib.import_module("onnxruntime")
        tokenizers = importlib.import_module("tokenizers")
        numpy = importlib.import_module("numpy")
    except ImportError as error:
        raise QwenError("Install the model packages: uv sync --locked --group models") from error
    for name in (WEIGHTS, TOKENIZER):
        if not (directory / name).is_file():
            raise QwenError(f"{directory / name} is missing: run make fetch-qwen-reranker")
    session = onnxruntime.InferenceSession(
        str(directory / WEIGHTS), providers=["CPUExecutionProvider"]
    )
    tokenizer = tokenizers.Tokenizer.from_file(str(directory / TOKENIZER))
    pad_id = tokenizer.token_to_id(END_OF_TEXT)
    if pad_id is None:
        raise QwenError(f"The tokenizer has no {END_OF_TEXT} token")

    class NumpyArrays:
        def ints(self, rows: list[list[int]]) -> object:
            return numpy.asarray(rows, dtype=numpy.int64)

    return QwenReranker(session, tokenizer, NumpyArrays(), pad_id)
