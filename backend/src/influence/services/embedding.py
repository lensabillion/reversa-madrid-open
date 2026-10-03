"""A meaning signal: embed texts as vectors, so a paraphrase lands near what it paraphrases.

Word overlap finds a copy and misses a rewording ("keep logs for six months" against
"retain records for half a year"). An embedding model maps a text to a vector so that texts
with the same meaning point the same way; the cosine of two unit vectors is their similarity.

Everything here is independent of the model: the embedder is a function passed in, so this
module and its tests need no model and no extra dependency. `services/qwen_onnx.py` supplies
the real one. Vectors are unit length, so cosine is a dot product (`math.sumprod`, in C).

Embedding is the slow step, so each text's vector is cached on disk by the hash of the model
and the text: a rerun, or a text that repeats, costs nothing. Cost: O(T) embedding calls for T
distinct texts, then O(P d) per search over P passages of d dimensions.
"""

import hashlib
import math
import sqlite3
from array import array
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from heapq import nlargest
from pathlib import Path

from influence.schemas.retrieval import SourcePassage
from influence.schemas.scoring import TextChange
from influence.services.scoring import changed_spans

type Vector = tuple[float, ...]
# Maps a batch of texts to one vector each, in order; the vectors need not be normalised.
type EmbedFunction = Callable[[Sequence[str]], Sequence[Sequence[float]]]

QUERY_INSTRUCTION = (
    "Given an amendment to an EU law, retrieve the submission passages that ask for the same change"
)
BATCH_SIZE = 16


class EmbeddingError(Exception):
    """The embedder returned something that is not one usable vector per text."""


def with_instruction(text: str, instruction: str = QUERY_INSTRUCTION) -> str:
    """Qwen3-Embedding's query format: the task is named in front of the query, not the document."""
    return f"Instruct: {instruction}\nQuery:{text}"


def unit(vector: Sequence[float]) -> Vector:
    """The vector scaled to length 1.

    Scaled by its largest entry first, so squaring cannot underflow to zero or overflow.
    """
    peak = max((abs(value) for value in vector), default=0.0)
    if not math.isfinite(peak) or peak == 0:
        raise EmbeddingError("The embedder returned a zero or non-finite vector")
    scaled = [value / peak for value in vector]
    norm = math.sqrt(math.sumprod(scaled, scaled))
    return tuple(value / norm for value in scaled)


def cosine(left: Vector, right: Vector) -> float:
    """Similarity of two unit vectors, in [-1, 1]; clamped so rounding cannot leave it."""
    return max(-1.0, min(1.0, math.sumprod(left, right)))


def delta_text(old: str | None, new: str) -> str:
    """What an amendment changes, as text: its inserted words, else its deleted words.

    With the original unknown the whole proposed text stands in, since no change can be
    told. Raises ValueError when the edit scorer's bounds (800 tokens a side) refuse the text.
    """
    if old is None:
        return new
    spans = changed_spans(TextChange(old=old, new=new))
    inserted = [span.text for span in spans if span.operation == "insert"]
    deleted = [span.text for span in spans if span.operation == "delete"]
    return " ".join(inserted or deleted)


def cache_key(model_id: str, text: str) -> str:
    """The cache row for `text` under `model_id`; another model never reads this model's row."""
    return hashlib.sha256(f"{model_id}\x00{text}".encode()).hexdigest()


class EmbeddingCache:
    """Vectors on disk, one row per (model, text) hash, in a SQLite file.

    Stored as 64-bit floats so a cached vector is identical to the one computed.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, vector BLOB NOT NULL)"
            )

    def load(self, keys: Sequence[str]) -> dict[str, Vector]:
        found: dict[str, Vector] = {}
        with closing(sqlite3.connect(self._path)) as connection:
            for key in keys:
                row = connection.execute(
                    "SELECT vector FROM vectors WHERE key = ?", (key,)
                ).fetchone()
                if row is not None:
                    values = array("d")
                    values.frombytes(row[0])
                    found[key] = tuple(values)
        return found

    def store(self, items: dict[str, Vector]) -> None:
        with closing(sqlite3.connect(self._path)) as connection, connection:
            connection.executemany(
                "INSERT OR REPLACE INTO vectors (key, vector) VALUES (?, ?)",
                [(key, array("d", vector).tobytes()) for key, vector in items.items()],
            )


def embed_texts(
    texts: Sequence[str],
    embed: EmbedFunction,
    *,
    model_id: str,
    cache: EmbeddingCache | None = None,
    batch_size: int = BATCH_SIZE,
) -> list[Vector]:
    """Unit vectors for `texts`, in order, embedding each distinct uncached text once.

    Misses are sent in batches of similar length, which keeps padding (wasted work) small.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    keys = {text: cache_key(model_id, text) for text in dict.fromkeys(texts)}
    known = cache.load(list(keys.values())) if cache is not None else {}
    missing = sorted((text for text, key in keys.items() if key not in known), key=len)
    for first in range(0, len(missing), batch_size):
        batch = missing[first : first + batch_size]
        vectors = embed(batch)
        if len(vectors) != len(batch):
            raise EmbeddingError(f"Asked for {len(batch)} vectors, got {len(vectors)}")
        fresh = {keys[text]: unit(vector) for text, vector in zip(batch, vectors, strict=True)}
        known.update(fresh)
        if cache is not None:
            cache.store(fresh)
    return [known[keys[text]] for text in texts]


@dataclass(frozen=True, slots=True)
class DenseHit:
    """One passage and how close its meaning is to the query's."""

    passage: SourcePassage
    rank: int
    score: float


class DenseIndex:
    """Passage vectors searched by cosine. A search is exact: it scores every passage."""

    def __init__(
        self,
        passages: Sequence[SourcePassage],
        embed: EmbedFunction,
        *,
        model_id: str,
        cache: EmbeddingCache | None = None,
        batch_size: int = BATCH_SIZE,
    ) -> None:
        self._passages = tuple(passages)
        self._embed = embed
        self._model_id = model_id
        self._cache = cache
        self._batch_size = batch_size
        self._vectors = embed_texts(
            [passage.text for passage in self._passages],
            embed,
            model_id=model_id,
            cache=cache,
            batch_size=batch_size,
        )

    def __len__(self) -> int:
        return len(self._passages)

    def search(
        self, query: str, k: int = 5, *, instruction: str | None = QUERY_INSTRUCTION
    ) -> tuple[DenseHit, ...]:
        """The `k` passages closest in meaning to `query`, best first; ties keep passage order.

        With an instruction the query is phrased as the retrieval task the model was trained
        on; pass None for a document-to-document comparison. O(P d + P log k).
        """
        if not query.strip():
            raise ValueError("The query has no text")
        text = query if instruction is None else with_instruction(query, instruction)
        (vector,) = embed_texts(
            [text], self._embed, model_id=self._model_id, cache=self._cache, batch_size=1
        )
        scored = ((cosine(vector, other), -index) for index, other in enumerate(self._vectors))
        best = nlargest(k, scored)
        return tuple(
            DenseHit(self._passages[-negative], rank, score)
            for rank, (score, negative) in enumerate(best, start=1)
        )
