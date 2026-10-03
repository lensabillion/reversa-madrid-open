"""Offline outputs must describe these exact source bytes and every evaluated pair."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from influence.practice.labels import PracticePair
from influence.repositories.lobbyplag import RawText
from influence.services.evaluation_artifacts import ArtifactKind, load_model_features

HASHES = {"amendments.json": "a" * 64, "proposals.json": "b" * 64}
PAIR = PracticePair(
    "c1",
    "a1",
    "p1",
    "org",
    RawText(old="", new="Protect café users"),
    RawText(old="", new="Protect café users"),
)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def fixture_files(
    tmp_path: Path, kind: ArtifactKind
) -> tuple[Path, Path, dict[str, object], dict[str, object]]:
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"schema": "embedding-inputs-1", "source_hashes": HASHES}))
    row: dict[str, object] = {"candidate_id": "c1"}
    payload: dict[str, object] = {
        "schema": "semantic-pairs-1" if kind == "semantic" else "local-nli-pairs-1",
        "model_id": "test/frozen-model",
        "revision": "c" * 40,
        "input_sha256": hashlib.sha256(inputs.read_bytes()).hexdigest(),
        "source_hashes": HASHES,
        "pairs": [row],
    }
    if kind == "semantic":
        row.update(
            {
                "amendment_id": "a1",
                "proposal_id": "p1",
                "amendment_key": digest("query\0INSERT: Protect café users"),
                "submission_key": digest("passage\0INSERT: Protect café users"),
                "cosine": 0.8,
                "missing_reason": None,
            }
        )
    else:
        row.update(
            {
                "premise_sha256": digest(PAIR.amendment.new),
                "hypothesis_sha256": digest(PAIR.submission.new),
                "contradiction": 0.1,
                "entailment": 0.7,
                "neutral": 0.2,
                "predicted": "entailment",
            }
        )
        payload.update(
            {
                "premise": "Full new amendment wording",
                "hypothesis": "Full new lobby proposal wording",
                "truncated_candidate_ids": ["c1", "synthetic-diagnostic"],
            }
        )
    return tmp_path / "artifact.json", inputs, payload, row


@pytest.mark.parametrize("kind", ["semantic", "judge"])
def test_exact_artifacts_load_features_and_provenance(tmp_path: Path, kind: ArtifactKind) -> None:
    path, inputs, payload, _ = fixture_files(tmp_path, kind)
    path.write_text(json.dumps(payload))
    result = load_model_features(
        path, kind=kind, inputs_path=inputs, source_hashes=HASHES, pairs=[PAIR]
    )
    expected = (
        {"semantic_cosine": 0.8}
        if kind == "semantic"
        else {"entailment_score": 0.7, "contradiction_score": 0.1}
    )
    assert result.features == {"c1": expected}
    assert result.provenance["artifact_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.provenance["revision"] == "c" * 40
    assert result.provenance["role"] == "development_features_only_not_publication_evidence"
    assert result.provenance["truncated_candidate_ids"] == (
        () if kind == "semantic" else ("c1", "synthetic-diagnostic")
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", "unknown"),
        ("model_id", " "),
        ("revision", "main"),
        ("input_sha256", "unknown"),
        ("source_hashes", {"file": "bad"}),
    ],
)
def test_metadata_requires_schema_model_pinned_revision_and_hashes(
    tmp_path: Path, field: str, value: object
) -> None:
    path, inputs, payload, _ = fixture_files(tmp_path, "semantic")
    payload[field] = value
    path.write_text(json.dumps(payload))
    with pytest.raises(ValidationError):
        load_model_features(
            path, kind="semantic", inputs_path=inputs, source_hashes=HASHES, pairs=[PAIR]
        )


@pytest.mark.parametrize(
    "mutation", ["artifact_sources", "input_sources", "input_bytes", "no_expected_sources"]
)
def test_stale_hashes_rejected(tmp_path: Path, mutation: str) -> None:
    path, inputs, payload, _ = fixture_files(tmp_path, "semantic")
    expected = HASHES
    if mutation == "artifact_sources":
        payload["source_hashes"] = {"other.json": "a" * 64}
    elif mutation == "input_sources":
        inputs.write_text(json.dumps({"schema": "embedding-inputs-1", "source_hashes": {}}))
        payload["input_sha256"] = hashlib.sha256(inputs.read_bytes()).hexdigest()
    elif mutation == "input_bytes":
        inputs.write_text(inputs.read_text() + " ")
    else:
        expected = {}
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="hashes"):
        load_model_features(
            path, kind="semantic", inputs_path=inputs, source_hashes=expected, pairs=[PAIR]
        )


@pytest.mark.parametrize(
    "mutation", ["duplicate", "missing", "extra", "empty_expected", "duplicate_expected"]
)
def test_candidate_coverage_is_exact(tmp_path: Path, mutation: str) -> None:
    path, inputs, payload, row = fixture_files(tmp_path, "semantic")
    pairs = [PAIR]
    if mutation == "duplicate":
        payload["pairs"] = [row, row]
    elif mutation == "missing":
        payload["pairs"] = []
    elif mutation == "extra":
        payload["pairs"] = [row, {**row, "candidate_id": "unknown"}]
    elif mutation == "empty_expected":
        pairs = []
    else:
        pairs = [PAIR, PAIR]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="coverage"):
        load_model_features(
            path, kind="semantic", inputs_path=inputs, source_hashes=HASHES, pairs=pairs
        )


@pytest.mark.parametrize(
    "field", ["amendment_id", "proposal_id", "amendment_key", "submission_key"]
)
def test_semantic_rows_bound_to_exact_text_and_identity(tmp_path: Path, field: str) -> None:
    path, inputs, payload, row = fixture_files(tmp_path, "semantic")
    row[field] = "d" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="text/identity mismatch"):
        load_model_features(
            path, kind="semantic", inputs_path=inputs, source_hashes=HASHES, pairs=[PAIR]
        )


@pytest.mark.parametrize("reason", [None, "No changed span on one side"])
def test_null_semantic_score_fails_with_recorded_reason(tmp_path: Path, reason: str | None) -> None:
    path, inputs, payload, row = fixture_files(tmp_path, "semantic")
    row.update({"cosine": None, "missing_reason": reason})
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match=reason or "no reason recorded"):
        load_model_features(
            path, kind="semantic", inputs_path=inputs, source_hashes=HASHES, pairs=[PAIR]
        )


@pytest.mark.parametrize("mutation", ["reason", "amendment_empty", "submission_empty"])
def test_score_cannot_coexist_with_missing_input(tmp_path: Path, mutation: str) -> None:
    path, inputs, payload, row = fixture_files(tmp_path, "semantic")
    pair = PAIR
    if mutation == "reason":
        row["missing_reason"] = "missing"
    elif mutation == "amendment_empty":
        pair = PracticePair(
            "c1", "a1", "p1", "org", RawText(old="same", new="same"), PAIR.submission
        )
        row["amendment_key"] = None
    else:
        pair = PracticePair(
            "c1", "a1", "p1", "org", PAIR.amendment, RawText(old="same", new="same")
        )
        row["submission_key"] = None
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="missing-input"):
        load_model_features(
            path, kind="semantic", inputs_path=inputs, source_hashes=HASHES, pairs=[pair]
        )


@pytest.mark.parametrize("field", ["premise_sha256", "hypothesis_sha256"])
def test_judge_hashes_bind_full_texts(tmp_path: Path, field: str) -> None:
    path, inputs, payload, row = fixture_files(tmp_path, "judge")
    row[field] = "d" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Judge pair text mismatch"):
        load_model_features(
            path, kind="judge", inputs_path=inputs, source_hashes=HASHES, pairs=[PAIR]
        )


@pytest.mark.parametrize(("field", "value"), [("neutral", 0.9), ("predicted", "contradiction")])
def test_judge_prediction_and_distribution_must_agree(
    tmp_path: Path, field: str, value: object
) -> None:
    path, inputs, payload, row = fixture_files(tmp_path, "judge")
    row[field] = value
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="inconsistent"):
        load_model_features(
            path, kind="judge", inputs_path=inputs, source_hashes=HASHES, pairs=[PAIR]
        )


@pytest.mark.parametrize("kind", ["semantic", "judge"])
def test_nonfinite_or_out_of_range_model_scores_rejected(
    tmp_path: Path, kind: ArtifactKind
) -> None:
    path, inputs, payload, row = fixture_files(tmp_path, kind)
    row["cosine" if kind == "semantic" else "entailment"] = 1.1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValidationError):
        load_model_features(path, kind=kind, inputs_path=inputs, source_hashes=HASHES, pairs=[PAIR])
