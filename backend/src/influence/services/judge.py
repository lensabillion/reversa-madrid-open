"""A meaning judge: does this passage ask for the change this amendment makes?

Words shared between an amendment and a passage are a clue, not an answer: "keep logs for six
months" and "retain records for half a year" share none, and "keep logs for at most thirty days"
shares nearly all and asks for something else. A reranker model reads both texts together and
answers yes or no. This module builds the question, turns the model's answer into a probability,
caches it, and finds the sentence of the passage that answers it best.

The model is a function passed in (`ScoreFunction`: prompts in, log-odds of "yes" out), so this
module and its tests need no model; `services/qwen_reranker.py` supplies the real one. The model
only scores; it writes no text. The evidence for a verdict is therefore chosen, never generated:
each sentence of the passage is judged on its own and the best one is returned with its exact
offsets, so the quotation is always a substring of the passage.

Cost: one model call per (amendment, passage) pair, and one per sentence for the evidence.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from influence.schemas.scoring import TextChange
from influence.services.embedding import EmbeddingCache, cache_key
from influence.services.passages import split_sentences
from influence.services.scoring import changed_spans

# Prompts -> the model's log-odds of "yes" for each, in order (positive means yes).
type ScoreFunction = Callable[[Sequence[str]], Sequence[float]]
type JudgedPair = tuple[str | None, str, str]

INSTRUCTION = "Does the passage ask for the same change that the amendment makes?"
_SYSTEM = (
    "Judge whether the Document meets the requirements based on the Query and the Instruct "
    'provided. Note that the answer can only be "yes" or "no".'
)
PREFIX = f"<|im_start|>system\n{_SYSTEM}<|im_end|>\n<|im_start|>user\n"
SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
# A field is cut here so a long amendment cannot push the answer prompt out of the model's reach.
# The cut is not silent: `clipped_fields` counts it, and the practice report publishes the count.
MAX_FIELD_CHARS = 1500
BATCH_SIZE = 1
_LOGIT_LIMIT = 30.0


class JudgeError(Exception):
    """The model returned something that is not one score per prompt."""


def _clip(text: str) -> str:
    stripped = text.strip()
    return stripped if not _too_long(text) else stripped[:MAX_FIELD_CHARS] + " ..."


def _too_long(text: str) -> bool:
    return len(text.strip()) > MAX_FIELD_CHARS


def amendment_query(old: str | None, new: str) -> str:
    """The amendment as old wording -> new wording; the new wording alone if the old is unknown."""
    if old is None:
        return f"Amendment, new wording (original unknown): {_clip(new)}"
    return f"Amendment: {_clip(old)} -> {_clip(new)}"


def change_query(old: str | None, new: str) -> str:
    """The amendment as only what it changes: the words it adds and the words it removes.

    A long paragraph with a few words changed can look the same as a passage that repeats the
    paragraph; naming the change keeps it in front of the model. Falls back to the old -> new
    form when the original is unknown or the text is past the edit scorer's bounds.
    """
    changes = _changes(old, new)
    if changes is None:
        return amendment_query(old, new)
    added, removed = changes
    parts = [f"adds: {_clip(added)}"] if added else []
    parts += [f"removes: {_clip(removed)}"] if removed else []
    return "Amendment " + "; ".join(parts) if parts else "Amendment makes no change"


def _changes(old: str | None, new: str) -> tuple[str, str] | None:
    """The words an amendment adds and removes; None when `change_query` falls back."""
    if old is None:
        return None
    try:
        spans = changed_spans(TextChange(old=old, new=new))
    except ValueError:
        return None
    added = " ".join(span.text for span in spans if span.operation == "insert")
    removed = " ".join(span.text for span in spans if span.operation == "delete")
    return added, removed


def clipped_fields(old: str | None, new: str, passage: str, *, changes_only: bool = False) -> int:
    """How many fields of `judge_prompt(old, new, passage)` are cut at `MAX_FIELD_CHARS`.

    The model never reads what follows a cut, so a caller that publishes scores counts the
    cut prompts instead of letting them pass unnoticed.
    """
    changes = _changes(old, new) if changes_only else None
    fields = list(changes) if changes is not None else ([] if old is None else [old]) + [new]
    return sum(_too_long(field) for field in (*fields, passage))


def judge_prompt(old: str | None, new: str, passage: str, *, changes_only: bool = False) -> str:
    """The reranker's question for one amendment and one passage, in its trained format."""
    query = change_query(old, new) if changes_only else amendment_query(old, new)
    return (
        f"{PREFIX}<Instruct>: {INSTRUCTION}\n<Query>: {query}\n<Document>: {_clip(passage)}{SUFFIX}"
    )


def probability(logit: float) -> float:
    """The chance of "yes" for a log-odds score, in [0, 1], without overflow."""
    clamped = max(-_LOGIT_LIMIT, min(_LOGIT_LIMIT, logit))
    return 1.0 / (1.0 + math.exp(-clamped))


def judge_pairs(
    pairs: Sequence[JudgedPair],
    score: ScoreFunction,
    *,
    model_id: str,
    cache: EmbeddingCache | None = None,
    batch_size: int = BATCH_SIZE,
    changes_only: bool = False,
) -> list[float]:
    """P(yes) for each (old, new, passage), in order; a repeated prompt is scored once.

    Scores are cached on disk by the hash of the prompt and the model, so a rerun costs nothing.
    With `changes_only` the amendment is shown as the words it adds and removes.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    prompts = [
        judge_prompt(old, new, passage, changes_only=changes_only) for old, new, passage in pairs
    ]
    keys = {prompt: cache_key(model_id, prompt) for prompt in dict.fromkeys(prompts)}
    known = cache.load(list(keys.values())) if cache is not None else {}
    missing = [prompt for prompt, key in keys.items() if key not in known]
    for first in range(0, len(missing), batch_size):
        batch = missing[first : first + batch_size]
        logits = score(batch)
        if len(logits) != len(batch):
            raise JudgeError(f"Asked for {len(batch)} scores, got {len(logits)}")
        fresh = {keys[prompt]: (float(logit),) for prompt, logit in zip(batch, logits, strict=True)}
        if any(not math.isfinite(logit) for (logit,) in fresh.values()):
            raise JudgeError("The model returned a non-finite score")
        known.update(fresh)
        if cache is not None:
            cache.store(fresh)
    return [probability(known[keys[prompt]][0]) for prompt in prompts]


@dataclass(frozen=True, slots=True)
class Evidence:
    """The sentence of a passage that best answers the question, with its exact offsets."""

    start: int
    end: int
    text: str
    probability: float


def best_sentence(
    old: str | None,
    new: str,
    passage: str,
    score: ScoreFunction,
    *,
    model_id: str,
    cache: EmbeddingCache | None = None,
    batch_size: int = BATCH_SIZE,
    changes_only: bool = False,
) -> Evidence:
    """Judge each sentence on its own and return the best, so the quote is a real substring.

    The first sentence wins a tie. `passage[start:end] == text`. Raises ValueError when the
    passage has no sentence.
    """
    sentences = split_sentences(passage)
    if not sentences:
        raise ValueError("The passage has no sentence to quote")
    chances = judge_pairs(
        [(old, new, passage[start:end]) for start, end, _ in sentences],
        score,
        model_id=model_id,
        cache=cache,
        batch_size=batch_size,
        changes_only=changes_only,
    )
    best = max(range(len(sentences)), key=lambda index: (chances[index], -index))
    start, end, _ = sentences[best]
    return Evidence(start, end, passage[start:end], chances[best])
