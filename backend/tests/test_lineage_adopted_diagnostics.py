"""Predeclared synthetic target diagnostics; direct requests do not evaluate BM25 recall.

The architecture reviewer froze the corpus before seeing any model output. These labels
are controlled scenario expectations, not a human real-law audit or an accuracy estimate.
Run this file to regenerate the deterministic hash manifest; no calls or credentials.
"""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from test_lineage_carrier_evidence import amendment, article

from influence.schemas.atlas import Ask, SourceSpan
from influence.services.jev import JevRequest
from influence.services.jev_judge import adopted_origin_request, judge_request, request_bytes
from influence.services.lineage import adopt_records

FIXTURE = Path(__file__).parent / "fixtures" / "lineage" / "adopted-origin-diagnostics.json"
MANIFEST = FIXTURE.with_name("adopted-origin-request-manifest.json")
CORPUS_SHA256 = "597d78a05fe42ab57eaf4bc2272ae6fe042295ddfae138a2dbfa7a6e453ad644"
PROPOSAL = "Baseline provisions unrelated to these diagnostics."


class DiagnosticCase(BaseModel):
    id: str
    category: str
    submission_text: str
    amendment_old: str | None
    amendment_new: str
    final_provision_text: str
    target_amendment_start: int
    target_amendment_end: int
    target_final_start: int
    target_final_end: int
    expected_surviving_relation: bool | Literal["unknown"]
    expected_request_skip: str | None = None
    rationale: str


class DiagnosticCorpus(BaseModel):
    cases: tuple[DiagnosticCase, ...]


def cases() -> tuple[DiagnosticCase, ...]:
    return DiagnosticCorpus.model_validate_json(FIXTURE.read_bytes()).cases


def diagnostic_request(case: DiagnosticCase) -> tuple[JevRequest | None, JevRequest | None]:
    item = amendment(1, case.amendment_new, old=case.amendment_old or "").model_copy(
        update={"old_text": case.amendment_old}
    )
    final = article(case.final_provision_text)
    adopted = adopt_records([item], [article(PROPOSAL, "proposal", "proposal"), final], [])
    targets = [
        e
        for adoption in adopted.adoptions
        for e in adoption.evidence
        if (e.amendment_span.start, e.amendment_span.end, e.final_span.start, e.final_span.end)
        == (
            case.target_amendment_start,
            case.target_amendment_end,
            case.target_final_start,
            case.target_final_end,
        )
    ]
    if case.expected_request_skip is not None:
        assert case.expected_request_skip == "no_adoption_evidence"
        assert targets == [], case.id
        return None, None
    assert len(targets) == 1, case.id
    source_id = f"doc:hys_attachment:{case.id}"
    ask = Ask(
        ask_id=f"ask:{case.id}",
        procedure_id=item.procedure_id,
        actor_id="actor:name:diagnostic",
        document_id=source_id,
        span=SourceSpan(
            record_id=source_id, start=0, end=len(case.submission_text), text=case.submission_text
        ),
        submitted_at=None,
        extraction_method="diagnostic-specification-v1",
    )
    request = adopted_origin_request(ask, item, targets[0], case.submission_text, final, {})
    assert isinstance(request, JevRequest), case.id
    legacy = judge_request(ask, item, case.submission_text, {})
    assert legacy is not None
    return request, legacy


def render_manifest() -> str:
    rows: list[dict[str, object]] = []
    for case in cases():
        request, legacy = diagnostic_request(case)
        rows.append(
            {
                "id": case.id,
                "category": case.category,
                "expected_surviving_relation": case.expected_surviving_relation,
                "expected_request_skip": case.expected_request_skip,
                "request_sha256": None
                if request is None
                else hashlib.sha256(request_bytes(request)).hexdigest(),
                "request_bytes": None if request is None else len(request_bytes(request)),
                "legacy_request_sha256": None
                if legacy is None
                else hashlib.sha256(request_bytes(legacy)).hexdigest(),
            }
        )
    return (
        json.dumps(
            {"corpus_sha256": CORPUS_SHA256, "prompt_revision": "adopted-origin-v1", "cases": rows},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )


def test_the_predeclared_corpus_is_frozen_and_each_target_is_structurally_verified() -> None:
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == CORPUS_SHA256
    corpus = cases()
    assert len(corpus) == 28
    assert len({case.id for case in corpus}) == 28
    assert sum(case.expected_surviving_relation is True for case in corpus) == 8
    assert sum(case.expected_surviving_relation is False for case in corpus) == 19
    assert sum(case.expected_surviving_relation == "unknown" for case in corpus) == 1
    assert sum(case.expected_request_skip is not None for case in corpus) == 4
    assert MANIFEST.read_text() == render_manifest()


if __name__ == "__main__":
    MANIFEST.write_text(render_manifest())
    print(f"Wrote {MANIFEST}")
