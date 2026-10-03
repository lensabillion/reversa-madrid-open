"""Run a frozen local NLI baseline, with diagnosis labels separate from model outputs.

LobbyPlag copy labels are not NLI labels. Its pairs receive raw scores for the parent's
organization-grouped evaluator only; this script never calls them entailment accuracy.
"""

import argparse
import hashlib
import json
import math
import platform
import time
from pathlib import Path
from typing import TypedDict, cast

import torch
from embed import Inputs
from model_io import write_json
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    PreTrainedModel,
    PreTrainedTokenizerBase,
)

MODEL_ID = "cross-encoder/nli-deberta-v3-small"
REVISION = "fa2804872c3b4bd748f38c0185cc85775361e735"


class Case(TypedDict):
    id: str
    premise: str
    hypothesis: str


class Cases(TypedDict):
    cases: list[Case]


def judge(input_path: Path, cases_path: Path, labels_path: Path, output: Path) -> None:
    inputs = cast(Inputs, json.loads(input_path.read_text()))
    cases = cast(Cases, json.loads(cases_path.read_text()))["cases"]
    pair_cases: list[Case] = [
        {
            "id": pair["candidate_id"],
            "premise": inputs["texts"][pair["amendment_full_key"]]["text"],
            "hypothesis": inputs["texts"][pair["submission_full_key"]]["text"],
        }
        for pair in inputs["pairs"]
    ]
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    # Torch leaves the seed parameter untyped; this boundary supplies an integer.
    torch.manual_seed(0)  # pyright: ignore[reportUnknownMemberType]
    torch.set_num_threads(4)
    # Transformers auto factories are dynamic; use its installed base-class interface.
    tokenizer = cast(
        PreTrainedTokenizerBase,
        AutoTokenizer.from_pretrained(  # pyright: ignore[reportUnknownMemberType]
            MODEL_ID, revision=REVISION, trust_remote_code=False, local_files_only=True
        ),
    )
    model = cast(
        PreTrainedModel,
        AutoModelForSequenceClassification.from_pretrained(  # pyright: ignore[reportUnknownMemberType]
            MODEL_ID,
            revision=REVISION,
            trust_remote_code=False,
            use_safetensors=True,
            local_files_only=True,
            dtype=torch.float32,
        ),
    )
    expected = {0: "contradiction", 1: "entailment", 2: "neutral"}
    if model.config.id2label != expected:
        raise ValueError(f"Unexpected model label mapping: {model.config.id2label}")
    # Use the inherited Torch interface; Transformers decorates to() with an invalid stub.
    cast(torch.nn.Module, model).to(device).eval()
    all_cases = [*pair_cases, *cases]
    results: list[dict[str, object]] = []
    truncated: list[str] = []
    started = time.perf_counter()
    for first in range(0, len(all_cases), 8):
        batch = all_cases[first : first + 8]
        premise, hypothesis = [c["premise"] for c in batch], [c["hypothesis"] for c in batch]
        lengths = cast(
            list[int],
            tokenizer(premise, hypothesis, truncation=False, return_length=True)["length"],
        )
        truncated.extend(
            case["id"] for case, length in zip(batch, lengths, strict=True) if length > 512
        )
        tokens = tokenizer(
            premise, hypothesis, padding=True, truncation=True, max_length=512, return_tensors="pt"
        ).to(device)
        with torch.inference_mode():
            logits = cast(torch.Tensor, model(**tokens).logits)
            probabilities = cast(list[list[float]], torch.softmax(logits, dim=-1).cpu().tolist())  # pyright: ignore[reportUnknownMemberType]
        for case, scores in zip(batch, probabilities, strict=True):
            if not all(math.isfinite(value) for value in scores):
                raise ValueError(f"Nonfinite judge scores for {case['id']}")
            predicted = expected[max(range(3), key=lambda index: scores[index])]
            results.append(
                {
                    "candidate_id": case["id"],
                    "premise_sha256": hashlib.sha256(case["premise"].encode()).hexdigest(),
                    "hypothesis_sha256": hashlib.sha256(case["hypothesis"].encode()).hexdigest(),
                    "contradiction": scores[0],
                    "entailment": scores[1],
                    "neutral": scores[2],
                    "predicted": predicted,
                }
            )
        if first % 80 == 0:
            print(
                {
                    "judge": MODEL_ID,
                    "scored": min(first + 8, len(all_cases)),
                    "total": len(all_cases),
                },
                flush=True,
            )
    metadata = {
        "schema": "local-nli-pairs-1",
        "model_id": MODEL_ID,
        "revision": REVISION,
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "source_hashes": inputs["source_hashes"],
        "device": device,
        "dtype": "float32",
        "premise": "Full new amendment wording",
        "hypothesis": "Full new lobby proposal wording",
        "seconds": time.perf_counter() - started,
        "hardware": platform.platform(),
        "torch": torch.__version__,
        "truncated_candidate_ids": truncated,
        "limitations": [
            "NLI scores are uncalibrated classifier outputs, not influence probabilities.",
            "Shared legal boilerplate can dominate full-text NLI.",
            "English generic NLI training is not validation of legal interpretation.",
        ],
    }
    write_json(output / "judge-pairs.json", {**metadata, "pairs": results[: len(pair_cases)]})
    write_json(
        output / "judge-diagnostic-output.json", {**metadata, "cases": results[len(pair_cases) :]}
    )
    expected_labels = cast(dict[str, dict[str, str]], json.loads(labels_path.read_text()))["labels"]
    diagnostics = [
        {
            **row,
            "expected": expected_labels[cast(str, row["candidate_id"])],
            "correct": row["predicted"] == expected_labels[cast(str, row["candidate_id"])],
        }
        for row in results[len(pair_cases) :]
    ]
    report = {
        **metadata,
        "diagnostic_count": len(diagnostics),
        "diagnostic_correct": sum(bool(row["correct"]) for row in diagnostics),
        "diagnostic_results": diagnostics,
        "interpretation": (
            "Synthetic intended-relation diagnostics only; "
            "not held-out legal accuracy or copy-label entailment accuracy."
        ),
    }
    write_json(output / "judge-diagnostic-report.json", report)
    print(
        {key: report[key] for key in ("diagnostic_count", "diagnostic_correct", "seconds")},
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument(
        "--cases", type=Path, default=Path(__file__).parent / "fixtures/judge-cases.json"
    )
    parser.add_argument(
        "--labels", type=Path, default=Path(__file__).parent / "fixtures/judge-labels.json"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    judge(args.inputs, args.cases, args.labels, args.out)
