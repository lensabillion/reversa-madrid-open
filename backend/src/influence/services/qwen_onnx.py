"""Qwen3-Embedding-0.6B on CPU through ONNX Runtime: texts in, one vector each out.

The model is a decoder-only transformer. To embed a text it reads the whole text and takes the
hidden state at the last token (the end-of-text token the tokenizer appends), which is then
scaled to length 1 by the caller. Batches are padded on the right: in a causal model a token
never sees what comes after it, so the padding cannot change a real token's state.

Measured on this export (8-bit weights, `model_int8.onnx`): the same text embedded alone twice
gives cosine 1.0, but alone versus with one other text gives 0.93 to 0.94, with left or right
padding alike. The 8-bit activations are quantised with a scale shared across the batch, so a
text's vector depends on what it is batched with. Embed one text per call (`BATCH_SIZE`) so
every vector is repeatable and a cached vector is the one a rerun would compute; it costs
about 40% of the throughput (24 against 40 texts a second on 16 cores).

The exported graph also wants a key-value cache for generation; for embedding that cache is
empty, so each input is given a zero-length one.

Only `load_qwen` imports the optional runtime (the `models` dependency group). Everything else
takes the session, the tokenizer and the array builders as arguments, so it is tested with fakes
and the default install needs no model packages. Files come from `make fetch-qwen-embedding`.
"""

import importlib
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, cast

MODEL_NAME = "qwen3-embedding-0.6b"
MODEL_ID = "qwen3-embedding-0.6b-onnx-int8@c25a394"
WEIGHTS = Path("onnx") / "model_int8.onnx"
TOKENIZER = Path("tokenizer.json")
END_OF_TEXT = "<|endoftext|>"
# Passages are about 200 tokens; a long amendment is cut here, keeping its end-of-text token.
# The cut is counted in `QwenEmbedder.truncated`, so a run can say how many texts it shortened.
MAX_TOKENS = 512
BATCH_SIZE = 1
CACHE_PREFIX = "past_key_values."
HIDDEN_STATE = "last_hidden_state"


class QwenError(Exception):
    """The model files or the runtime are not usable."""


class _Encoding(Protocol):
    @property
    def ids(self) -> Sequence[int]: ...


class Tokenizer(Protocol):
    def encode_batch(self, inputs: list[str]) -> Sequence[_Encoding]: ...


class _GraphInput(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def shape(self) -> Sequence[object]: ...


class Session(Protocol):
    def get_inputs(self) -> Sequence[_GraphInput]: ...

    def run(self, output_names: list[str], input_feed: dict[str, object]) -> Sequence[object]: ...


class Arrays(Protocol):
    """Builds the runtime's arrays, so this module never imports the runtime itself."""

    def ints(self, rows: list[list[int]]) -> object: ...

    def empty_cache(self, batch: int, heads: int, head_dim: int) -> object: ...


def _truncate(ids: Sequence[int]) -> list[int]:
    if len(ids) <= MAX_TOKENS:
        return list(ids)
    return [*ids[: MAX_TOKENS - 1], ids[-1]]


class QwenEmbedder:
    """Callable `EmbedFunction`: `embedder(texts)` returns one raw vector per text.

    `truncated` counts the texts this embedder has cut at `MAX_TOKENS` so far (a text passed
    twice counts twice), so callers can report the cut instead of hiding it.
    """

    def __init__(self, session: Session, tokenizer: Tokenizer, arrays: Arrays, pad_id: int) -> None:
        self._session = session
        self._tokenizer = tokenizer
        self._arrays = arrays
        self._pad_id = pad_id
        self.truncated = 0
        self._cache_inputs = [
            item for item in session.get_inputs() if item.name.startswith(CACHE_PREFIX)
        ]

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        encodings = self._tokenizer.encode_batch(list(texts))
        self.truncated += sum(len(encoding.ids) > MAX_TOKENS for encoding in encodings)
        rows = [_truncate(encoding.ids) for encoding in encodings]
        width = max(len(row) for row in rows)
        ids = [row + [self._pad_id] * (width - len(row)) for row in rows]
        mask = [[1] * len(row) + [0] * (width - len(row)) for row in rows]
        positions = [list(range(len(row))) + [0] * (width - len(row)) for row in rows]
        feed: dict[str, object] = {
            "input_ids": self._arrays.ints(ids),
            "attention_mask": self._arrays.ints(mask),
            "position_ids": self._arrays.ints(positions),
        }
        for item in self._cache_inputs:
            heads, head_dim = item.shape[1], item.shape[3]
            if not isinstance(heads, int) or not isinstance(head_dim, int):
                raise QwenError(f"Cache input {item.name} has no fixed head shape")
            feed[item.name] = self._arrays.empty_cache(len(rows), heads, head_dim)
        hidden = self._session.run([HIDDEN_STATE], feed)[0]
        return [_state_at(hidden, row, len(rows[row]) - 1) for row in range(len(rows))]


def _state_at(hidden: object, row: int, position: int) -> list[float]:
    """The hidden state of `row` at `position`, as floats.

    `hidden` is the runtime's batch x tokens x dimensions array; only indexing is used, so a
    nested list stands in for it in tests.
    """
    rows = cast("Sequence[Sequence[Sequence[float]]]", hidden)
    return [float(value) for value in rows[row][position]]


def load_qwen(directory: Path) -> QwenEmbedder:  # pragma: no cover
    """Open the model in `directory` (see `scripts/fetch_qwen_embedding.py`) on the CPU.

    The only function that imports the optional `models` group: onnxruntime and tokenizers.
    Excluded from coverage because the default install does not have them; the logic it
    hands them to is tested.
    """
    try:
        onnxruntime = importlib.import_module("onnxruntime")
        tokenizers = importlib.import_module("tokenizers")
        numpy = importlib.import_module("numpy")
    except ImportError as error:
        raise QwenError("Install the model packages: uv sync --locked --group models") from error
    for name in (WEIGHTS, TOKENIZER):
        if not (directory / name).is_file():
            raise QwenError(f"{directory / name} is missing: run make fetch-qwen-embedding")
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

        def empty_cache(self, batch: int, heads: int, head_dim: int) -> object:
            return numpy.zeros((batch, heads, 0, head_dim), dtype=numpy.float32)

    return QwenEmbedder(session, tokenizer, NumpyArrays(), pad_id)
