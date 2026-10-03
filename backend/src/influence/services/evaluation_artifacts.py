"""Validate offline model evidence against the exact practice inputs before evaluation.

Hashes detect stale or mismatched artifacts, not dishonest metadata. These loaders never
infer missing scores or make a development artifact eligible for publication.
"""

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isclose
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from influence.practice.labels import PracticePair
from influence.schemas.scoring import TextChange
from influence.services.scoring import changed_spans

type ArtifactKind = Literal["semantic", "judge"]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Revision = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Support = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class _Record(BaseModel):
    # The isolated runners also record hardware/timing and diagnostic fields.
    model_config = ConfigDict(extra="allow", frozen=True)


class _Inputs(_Record):
    schema_: Literal["embedding-inputs-1"] = Field(alias="schema")
    source_hashes: dict[str, Digest]


class _Metadata(_Record):
    model_id: Name
    revision: Revision
    input_sha256: Digest
    source_hashes: dict[str, Digest]


class _SemanticRow(_Record):
    candidate_id: Name
    amendment_id: Name
    proposal_id: Name
    amendment_key: Digest | None
    submission_key: Digest | None
    cosine: Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)] | None
    missing_reason: str | None


class _SemanticArtifact(_Metadata):
    schema_: Literal["semantic-pairs-1"] = Field(alias="schema")
    pairs: tuple[_SemanticRow, ...]


class _JudgeRow(_Record):
    candidate_id: Name
    premise_sha256: Digest
    hypothesis_sha256: Digest
    contradiction: Support
    entailment: Support
    neutral: Support
    predicted: Literal["contradiction", "entailment", "neutral"]


class _JudgeArtifact(_Metadata):
    schema_: Literal["local-nli-pairs-1"] = Field(alias="schema")
    premise: Literal["Full new amendment wording"]
    hypothesis: Literal["Full new lobby proposal wording"]
    truncated_candidate_ids: tuple[str, ...]
    pairs: tuple[_JudgeRow, ...]


@dataclass(frozen=True)
class ModelFeatures:
    features: Mapping[str, Mapping[str, float]]
    provenance: Mapping[str, object]


def _delta_key(old: str, new: str, role: str) -> str | None:
    spans = changed_spans(TextChange(old=old, new=new))
    if not spans:
        return None
    text = "\n".join(f"{span.operation.upper()}: {span.text}" for span in spans)
    return hashlib.sha256(f"{role}\0{text}".encode()).hexdigest()


def load_model_features(
    path: Path,
    *,
    kind: ArtifactKind,
    inputs_path: Path,
    source_hashes: Mapping[str, str],
    pairs: Sequence[PracticePair],
) -> ModelFeatures:
    """Require complete, exact pair coverage and frozen input provenance; fail closed.

    O(N*T²) for N semantic pairs of at most T=800 tokens per side (existing token diff);
    judge hashes and joins are linear in input bytes. Neither branch loads model weights.
    """
    raw = path.read_bytes()
    artifact = (
        _SemanticArtifact.model_validate_json(raw)
        if kind == "semantic"
        else _JudgeArtifact.model_validate_json(raw)
    )
    input_bytes = inputs_path.read_bytes()
    inputs = _Inputs.model_validate_json(input_bytes)
    if (
        not source_hashes
        or artifact.source_hashes != source_hashes
        or inputs.source_hashes != source_hashes
        or artifact.input_sha256 != hashlib.sha256(input_bytes).hexdigest()
    ):
        raise ValueError("Model artifact/input hashes do not match the current dataset")
    expected = {pair.candidate_id: pair for pair in pairs}
    actual = [row.candidate_id for row in artifact.pairs]
    if (
        not expected
        or len(expected) != len(pairs)
        or len(set(actual)) != len(actual)
        or set(actual) != set(expected)
    ):
        raise ValueError("Model artifact needs exact, unique, nonempty practice candidate coverage")
    features: dict[str, dict[str, float]] = {}
    if isinstance(artifact, _SemanticArtifact):
        for row in artifact.pairs:
            pair = expected[row.candidate_id]
            if (
                row.amendment_id != pair.amendment_id
                or row.proposal_id != pair.proposal_id
                or row.amendment_key != _delta_key(pair.amendment.old, pair.amendment.new, "query")
                or row.submission_key
                != _delta_key(pair.submission.old, pair.submission.new, "passage")
            ):
                raise ValueError(f"Semantic pair text/identity mismatch: {row.candidate_id}")
            if row.cosine is None:
                raise ValueError(
                    f"Missing semantic score for {row.candidate_id}: "
                    f"{row.missing_reason or 'no reason recorded'}; no zero fallback permitted"
                )
            if (
                row.missing_reason is not None
                or row.amendment_key is None
                or row.submission_key is None
            ):
                raise ValueError(f"Semantic score has missing-input metadata: {row.candidate_id}")
            features[row.candidate_id] = {"semantic_cosine": row.cosine}
        truncated: tuple[str, ...] = ()
    else:
        for row in artifact.pairs:
            pair = expected[row.candidate_id]
            if (
                row.premise_sha256 != hashlib.sha256(pair.amendment.new.encode()).hexdigest()
                or row.hypothesis_sha256 != hashlib.sha256(pair.submission.new.encode()).hexdigest()
            ):
                raise ValueError(f"Judge pair text mismatch: {row.candidate_id}")
            scores = {
                "contradiction": row.contradiction,
                "entailment": row.entailment,
                "neutral": row.neutral,
            }
            if not isclose(sum(scores.values()), 1.0, abs_tol=1e-5) or scores[row.predicted] != max(
                scores.values()
            ):
                raise ValueError(f"Judge scores/prediction are inconsistent: {row.candidate_id}")
            features[row.candidate_id] = {
                "entailment_score": row.entailment,
                "contradiction_score": row.contradiction,
            }
        # The runner also reports truncated synthetic diagnostics; retain them explicitly.
        truncated = artifact.truncated_candidate_ids
    return ModelFeatures(
        features=features,
        provenance={
            "kind": kind,
            "artifact_sha256": hashlib.sha256(raw).hexdigest(),
            "model_id": artifact.model_id,
            "revision": artifact.revision,
            "input_sha256": artifact.input_sha256,
            "source_hashes": artifact.source_hashes,
            "candidate_count": len(actual),
            "truncated_candidate_ids": truncated,
            "role": "development_features_only_not_publication_evidence",
        },
    )
