"""Frozen local embeddings and retrieval measurements; model outputs never contain labels.

Run in backend/models' locked runtime. Model code comes from installed Transformers;
remote code and pickle weights are disabled. Only completed artifacts are published.
"""

import argparse
import hashlib
import json
import math
import platform
import time
from pathlib import Path
from typing import Literal, TypedDict, cast

import torch
import torch.nn.functional as functional
from model_io import text_key, write_json
from transformers import AutoModel, AutoTokenizer, PreTrainedModel, PreTrainedTokenizerBase

MODELS = {
    "qwen": ("Qwen/Qwen3-Embedding-0.6B", "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"),
    "e5": ("intfloat/multilingual-e5-small", "614241f622f53c4eeff9890bdc4f31cfecc418b3"),
}
INSTRUCTION = (
    "Given a legislative amendment change, retrieve lobby proposals "
    "requesting the same legal change."
)


class TextInput(TypedDict):
    role: Literal["query", "passage"]
    text: str


class CorpusEntry(TypedDict):
    id: str
    key: str | None


class PairInput(TypedDict):
    candidate_id: str
    amendment_id: str
    proposal_id: str
    amendment_key: str | None
    submission_key: str | None
    amendment_full_key: str
    submission_full_key: str


class RankEntry(TypedDict):
    proposal_id: str
    rank: int
    score: float


class Inputs(TypedDict):
    schema: str
    source_hashes: dict[str, str]
    texts: dict[str, TextInput]
    proposals: list[CorpusEntry]
    amendments: list[CorpusEntry]
    pairs: list[PairInput]
    bm25: dict[str, list[RankEntry]]


class Label(TypedDict):
    candidate_id: str
    amendment_id: str
    proposal_id: str
    positive: bool
    organization_id: str


class Labels(TypedDict):
    schema: str
    source_hashes: dict[str, str]
    pairs: list[Label]


def prompt(name: str, entry: TextInput) -> str:
    if name == "e5":
        return f"{entry['role']}: {entry['text']}"
    if entry["role"] == "query":
        return f"Instruct: {INSTRUCTION}\nQuery:{entry['text']}"
    return entry["text"]


def pool(hidden: torch.Tensor, mask: torch.Tensor, name: str) -> torch.Tensor:
    """Qwen uses last-token pooling with left padding; E5 uses masked mean pooling."""
    if name == "qwen":
        pooled = hidden[:, -1]
    else:
        masked = hidden.masked_fill(~mask[..., None].bool(), 0)
        pooled = masked.sum(dim=1) / mask.sum(dim=1)[..., None]
    return functional.normalize(pooled.float(), p=2, dim=1)


def evaluate(
    inputs: Inputs, embeddings: dict[str, list[float]], labels_path: Path
) -> dict[str, object]:
    """Exact ID recall@20 over the full corpus; ties sort by proposal ID. O(Q P D)."""
    labels = cast(Labels, json.loads(labels_path.read_text()))
    if labels["source_hashes"] != inputs["source_hashes"]:
        raise ValueError("Labels and embeddings refer to different public source files")
    proposal_ids = [item["id"] for item in inputs["proposals"]]
    corpus = torch.tensor([embeddings[cast(str, item["key"])] for item in inputs["proposals"]])
    dense: dict[str, list[str]] = {}
    fusion: dict[str, list[str]] = {}
    for query in inputs["amendments"]:
        lexical = inputs["bm25"][query["id"]][:20]
        if query["key"] is None:
            dense[query["id"]] = []
        else:
            scores = cast(list[float], (corpus @ torch.tensor(embeddings[query["key"]])).tolist())  # pyright: ignore[reportUnknownMemberType]
            order = sorted(range(len(proposal_ids)), key=lambda i: (-scores[i], proposal_ids[i]))
            dense[query["id"]] = [proposal_ids[i] for i in order[:20]]
        ranks: dict[str, float] = {}
        for rank, proposal_id in enumerate(dense[query["id"]], start=1):
            ranks[proposal_id] = 1 / (60 + rank)
        for item in lexical:
            ranks[item["proposal_id"]] = ranks.get(item["proposal_id"], 0) + 1 / (60 + item["rank"])
        fusion[query["id"]] = sorted(ranks, key=lambda key: (-ranks[key], key))[:20]
    positives = [item for item in labels["pairs"] if item["positive"]]
    if not positives:
        raise ValueError("Retrieval evaluation requires positive pairs")
    results: list[dict[str, object]] = []
    for item in positives:
        query_id, proposal_id = item["amendment_id"], item["proposal_id"]
        lexical = [entry["proposal_id"] for entry in inputs["bm25"][query_id][:20]]
        results.append(
            {
                "candidate_id": item["candidate_id"],
                "amendment_id": query_id,
                "proposal_id": proposal_id,
                "organization_id": item["organization_id"],
                "bm25_hit": proposal_id in lexical,
                "dense_hit": proposal_id in dense[query_id],
                "rrf_hit": proposal_id in fusion[query_id],
            }
        )
    return {
        "positive_pairs": len(positives),
        "proposal_pool": len(proposal_ids),
        "k": 20,
        "bm25_recall_at_20": sum(bool(row["bm25_hit"]) for row in results) / len(results),
        "dense_recall_at_20": sum(bool(row["dense_hit"]) for row in results) / len(results),
        "rrf_recall_at_20": sum(bool(row["rrf_hit"]) for row in results) / len(results),
        "rrf_constant": 60,
        "rrf_input_top_k": 20,
        "verified_pairs": results,
        "limitations": [
            "Model selection on one historical GDPR corpus, not independent validation.",
            "Exact proposal-ID recall penalizes tied identical proposal texts.",
            "Unlabelled proposals are retrieval distractors, not assumed negative labels.",
        ],
    }


def run(
    name: str,
    input_path: Path,
    output: Path,
    labels: Path,
    device: str,
    batch_size: int,
    max_length: int,
    reuse: Path | None = None,
) -> None:
    inputs = cast(Inputs, json.loads(input_path.read_text()))
    if inputs["schema"] != "embedding-inputs-1" or not inputs["texts"]:
        raise ValueError("Missing or incompatible embedding inputs")
    for key, entry in inputs["texts"].items():
        if entry["role"] not in ("query", "passage") or key != text_key(
            entry["role"], entry["text"]
        ):
            raise ValueError(f"Invalid text identity: {key}")
    if device == "mps" and not torch.backends.mps.is_available():
        raise ValueError("Requested MPS device is unavailable")
    # Torch leaves the seed parameter untyped; this boundary supplies an integer.
    torch.manual_seed(0)  # pyright: ignore[reportUnknownMemberType]
    torch.set_num_threads(4)
    model_id, revision = MODELS[name]
    started = time.perf_counter()
    # Transformers auto factories are dynamic; use its installed base-class interface.
    tokenizer = cast(
        PreTrainedTokenizerBase,
        AutoTokenizer.from_pretrained(  # pyright: ignore[reportUnknownMemberType]
            model_id,
            revision=revision,
            trust_remote_code=False,
            local_files_only=True,
            padding_side="left" if name == "qwen" else "right",
        ),
    )
    model = cast(
        PreTrainedModel,
        AutoModel.from_pretrained(  # pyright: ignore[reportUnknownMemberType]
            model_id,
            revision=revision,
            trust_remote_code=False,
            local_files_only=True,
            use_safetensors=True,
            dtype=torch.float16 if device == "mps" else torch.float32,
        ),
    )
    model.config.use_cache = False
    # Use the inherited Torch interface; Transformers decorates to() with an invalid stub.
    cast(torch.nn.Module, model).to(device).eval()
    load_seconds = time.perf_counter() - started
    ordered = sorted(inputs["texts"], key=lambda key: (len(inputs["texts"][key]["text"]), key))
    embeddings: dict[str, list[float]] = {}
    truncated: list[str] = []
    if reuse is not None:
        cached = json.loads(reuse.read_text())
        expected = {
            "schema": "semantic-embeddings-1",
            "model_id": model_id,
            "revision": revision,
            "max_length": max_length,
            "source_hashes": inputs["source_hashes"],
            "query_instruction": INSTRUCTION if name == "qwen" else "query: / passage: prefixes",
            "pooling": "last_token" if name == "qwen" else "masked_mean",
            "dtype": "float16" if device == "mps" else "float32",
            "normalized": True,
        }
        if any(cached.get(key) != value for key, value in expected.items()):
            raise ValueError("Cached embeddings do not match the frozen run configuration")
        dimension = 1024 if name == "qwen" else 384
        for key, vector in cached["embeddings"].items():
            if key in inputs["texts"]:
                if (
                    len(vector) != dimension
                    or not all(math.isfinite(value) for value in vector)
                    or abs(sum(value * value for value in vector) - 1) > 0.0001
                ):
                    raise ValueError(f"Invalid cached embedding: {key}")
                embeddings[key] = vector
        truncated = [key for key in cached["truncated_input_keys"] if key in inputs["texts"]]
    reused = len(embeddings)
    ordered = [key for key in ordered if key not in embeddings]
    embedding_started = time.perf_counter()
    for first in range(0, len(ordered), batch_size):
        keys = ordered[first : first + batch_size]
        texts = [prompt(name, inputs["texts"][key]) for key in keys]
        lengths = cast(
            list[int],
            tokenizer(texts, truncation=False, padding=False, return_length=True)["length"],
        )
        truncated.extend(
            key for key, length in zip(keys, lengths, strict=True) if length > max_length
        )
        tokens = tokenizer(
            texts, padding=True, truncation=True, max_length=max_length, return_tensors="pt"
        ).to(device)
        with torch.inference_mode():
            vectors = pool(
                cast(torch.Tensor, model(**tokens).last_hidden_state),
                tokens["attention_mask"],
                name,
            ).cpu()
        rows = cast(list[list[float]], vectors.tolist())  # pyright: ignore[reportUnknownMemberType]
        for key, vector in zip(keys, rows, strict=True):
            if not all(math.isfinite(value) for value in vector):
                raise ValueError(f"Nonfinite embedding for {key}")
            embeddings[key] = [round(value, 8) for value in vector]
        if first % (batch_size * 10) == 0 or first + batch_size >= len(ordered):
            print(
                {
                    "model": name,
                    "encoded": min(first + batch_size, len(ordered)),
                    "total": len(ordered),
                    "seconds": round(time.perf_counter() - embedding_started, 2),
                },
                flush=True,
            )
    embedding_seconds = time.perf_counter() - embedding_started
    metadata = {
        "schema": "semantic-embeddings-1",
        "model_id": model_id,
        "revision": revision,
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "source_hashes": inputs["source_hashes"],
        "key_format": "sha256(role + NUL + raw_text)",
        "query_instruction": INSTRUCTION if name == "qwen" else "query: / passage: prefixes",
        "pooling": "last_token" if name == "qwen" else "masked_mean",
        "normalized": True,
        "max_length": max_length,
        "dimension": len(next(iter(embeddings.values()))),
        "dtype": "float16" if device == "mps" else "float32",
        "device": device,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "hardware": platform.platform(),
        "load_seconds": load_seconds,
        "embedding_seconds": embedding_seconds,
        "truncated_input_keys": truncated,
        "batch_size": batch_size,
        "reused_embeddings": reused,
        "encoded_embeddings": len(ordered),
    }
    write_json(output / "embeddings.json", {**metadata, "embeddings": embeddings})
    pairs: list[dict[str, object]] = []
    for pair in inputs["pairs"]:
        left, right = pair["amendment_key"], pair["submission_key"]
        cosine = (
            sum(a * b for a, b in zip(embeddings[left], embeddings[right], strict=True))
            if left and right
            else None
        )
        pairs.append(
            {
                **pair,
                "cosine": max(-1.0, min(1.0, cosine)) if cosine is not None else None,
                "missing_reason": "No changed span on one side" if cosine is None else None,
            }
        )
    write_json(
        output / "semantic-pairs.json", {**metadata, "schema": "semantic-pairs-1", "pairs": pairs}
    )
    report = {**metadata, **evaluate(inputs, embeddings, labels)}
    write_json(output / "retrieval-report.json", report)
    print(
        {
            key: report[key]
            for key in (
                "model_id",
                "positive_pairs",
                "proposal_pool",
                "dense_recall_at_20",
                "bm25_recall_at_20",
                "rrf_recall_at_20",
                "embedding_seconds",
            )
        },
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=tuple(MODELS), required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reuse-embeddings", type=Path)
    parser.add_argument("--device", choices=("mps", "cpu"), default="mps")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=512)
    args = parser.parse_args()
    if args.batch_size < 1 or not 1 <= args.max_length <= 512:
        parser.error("batch-size must be positive; max-length must be between1 and512")
    run(
        args.model,
        args.inputs,
        args.out,
        args.labels,
        args.device,
        args.batch_size,
        args.max_length,
        args.reuse_embeddings,
    )
