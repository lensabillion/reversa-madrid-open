"""Small offline checks of pooling, provenance and retrieval accounting, without weights."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import pytest
import torch
from embed import Inputs, evaluate, pool, prompt
from model_io import text_key, write_json


class TestRuntime:
    def test_pooling_excludes_padding_and_normalizes(self) -> None:
        hidden = torch.tensor([[[99.0, 99.0], [3.0, 4.0]]])
        mask = torch.tensor([[0, 1]])
        expected = torch.tensor([[0.6, 0.8]])
        assert torch.allclose(pool(hidden, mask, "qwen"), expected)
        assert torch.allclose(pool(hidden, mask, "e5"), expected)
        assert torch.allclose(
            pool(torch.tensor([[[1.0, 0.0], [0.0, 1.0]]]), torch.tensor([[1, 1]]), "e5"),
            torch.tensor([[2 ** (-0.5), 2 ** (-0.5)]]),
        )

    def test_prompt_and_identity_preserve_role_and_raw_text(self) -> None:
        query = {"role": "query", "text": "DELETE: must"}
        assert text_key("query", "DELETE: must") != text_key("passage", "DELETE: must")
        assert prompt("e5", {"role": "query", "text": query["text"]}) == "query: DELETE: must"
        assert "Query:DELETE: must" in prompt("qwen", {"role": "query", "text": query["text"]})
        assert prompt("qwen", {"role": "passage", "text": query["text"]}) == "DELETE: must"

    def test_atomic_output_rejects_nan_without_replacing_result(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            write_json(path, {"result": 1})
            with pytest.raises(ValueError, match="Out of range float"):
                write_json(path, {"result": float("nan")})
            assert json.loads(path.read_text()) == {"result": 1}
            assert list(Path(directory).iterdir()) == [path]

    def test_recall_counts_missing_queries_as_misses_and_checks_sources(self) -> None:
        inputs = cast(
            Inputs,
            {
                "source_hashes": {"file": "same"},
                "proposals": [{"id": "p", "key": "p"}],
                "amendments": [{"id": "a", "key": "a"}, {"id": "empty", "key": None}],
                "bm25": {"a": [{"proposal_id": "p", "rank": 1, "score": 0.2}], "empty": []},
            },
        )
        with TemporaryDirectory() as directory:
            labels = Path(directory) / "labels.json"
            rows = [
                {
                    "candidate_id": key,
                    "amendment_id": key,
                    "proposal_id": "p",
                    "positive": True,
                    "organization_id": "org",
                }
                for key in ("a", "empty")
            ]
            write_json(labels, {"source_hashes": {"file": "same"}, "pairs": rows})
            report = evaluate(inputs, {"p": [1.0, 0.0], "a": [1.0, 0.0]}, labels)
            assert report["positive_pairs"] == 2
            assert report["dense_recall_at_20"] == 0.5
            assert report["bm25_recall_at_20"] == 0.5
            assert report["rrf_recall_at_20"] == 0.5
            write_json(labels, {"source_hashes": {"file": "changed"}, "pairs": rows})
            with pytest.raises(ValueError, match="different public source"):
                evaluate(inputs, {"p": [1.0, 0.0]}, labels)
            write_json(labels, {"source_hashes": {"file": "same"}, "pairs": []})
            with pytest.raises(ValueError, match="requires positive pairs"):
                evaluate(inputs, {"p": [1.0, 0.0], "a": [1.0, 0.0]}, labels)
