"""Rehearse the shared synthetic fixtures; this is not a live-source evaluation."""

import json
import platform
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel

from influence.schemas.atlas import (
    Actor,
    Amendment,
    ArticleVersion,
    Ask,
    DocumentText,
    GraphSnapshot,
    LawRecord,
    LinkAssessment,
    Outcome,
    Passage,
    SourceDocument,
)
from influence.services.atlas_analysis import OutcomeAnalysis, aggregate_outcomes
from influence.services.atlas_graph import build_graph

fixture_root = Path(__file__).resolve().parents[1] / "tests/fixtures/atlas"


def read[T: BaseModel](name: str, model: type[T]) -> list[T]:
    return [
        model.model_validate_json(line)
        for line in (fixture_root / f"{name}.jsonl").read_text().splitlines()
    ]


laws = read("laws", LawRecord)
actors = read("actors", Actor)
asks = read("asks", Ask)
outcomes = read("outcomes", Outcome)
documents = read("documents", SourceDocument)
document_texts = read("document_texts", DocumentText)
passages = read("passages", Passage)
amendments = read("amendments", Amendment)
articles = read("articles", ArticleVersion)
links = read("links", LinkAssessment)


def run() -> tuple[GraphSnapshot, OutcomeAnalysis]:
    graph = build_graph(
        snapshot_id="snapshot:consumer-rehearsal",
        run_id="run:consumer-rehearsal",
        generated_at=datetime(2026, 10, 3, tzinfo=UTC),
        laws=laws,
        actors=actors,
        asks=asks,
        outcomes=outcomes,
        documents=documents,
        document_texts=document_texts,
        passages=passages,
        amendments=amendments,
        articles=articles,
        links=links,
    )
    analysis = aggregate_outcomes(laws=laws, actors=actors, asks=asks, outcomes=outcomes)
    return graph, analysis


graph, analysis = run()
start = perf_counter()
iterations = 1000
for _ in range(iterations):
    run()
elapsed = perf_counter() - start
output = {
    "source": "Committed synthetic atlas-1 fixtures; not real influence findings",
    "snapshot": graph.model_dump(mode="json"),
    "rows": [asdict(row) for row in analysis.rows],
    "totals": [asdict(counts) for counts in analysis.totals],
}
print(
    json.dumps(
        {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "laws": len(laws),
            "asks": len(asks),
            "links": len(links),
            "outcomes": len(outcomes),
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "totals": output["totals"],
            "iterations": iterations,
            "elapsed_seconds": round(elapsed, 4),
            "milliseconds_per_run": round(elapsed * 1000 / iterations, 4),
        },
        indent=2,
    )
)
