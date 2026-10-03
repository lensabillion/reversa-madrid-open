"""Prepare public texts with the application's validated loader; no model code runs here.

Run with the main backend environment. Candidate labels are a separate artifact and
are never passed to the embedding model. All proposals form the retrieval corpus;
queries are the unique amendments in the existing labelled practice set.
"""

import argparse
import hashlib
from pathlib import Path

from model_io import text_key, write_json

from influence.practice.labels import build_practice_set

# Share the measured baseline corpus construction instead of creating a divergent copy.
from influence.practice.recall import (
    _build_index,  # pyright: ignore[reportPrivateUsage]
    _passage_text,  # pyright: ignore[reportPrivateUsage]
)
from influence.repositories.lobbyplag import DemoRepository
from influence.schemas.scoring import TextChange
from influence.services.scoring import changed_spans


def prepare(directory: Path, output: Path) -> None:
    repository = DemoRepository.load(directory)
    practice = build_practice_set(repository)
    texts: dict[str, dict[str, str]] = {}

    def add(role: str, text: str) -> str:
        key = text_key(role, text)
        texts[key] = {"role": role, "text": text}
        return key

    proposals = [
        {"id": proposal.uid, "key": add("passage", text)}
        for _, proposal in sorted(repository.proposals.items())
        if (text := _passage_text(proposal.text, "new_or_deleted_text")).strip()
    ]

    def delta(old: str, new: str, role: str) -> str | None:
        spans = changed_spans(TextChange(old=old, new=new))
        return (
            add(role, "\n".join(f"{span.operation.upper()}: {span.text}" for span in spans))
            if spans
            else None
        )

    amendments = {
        item.pair.amendment_id: delta(item.pair.amendment.old, item.pair.amendment.new, "query")
        for item in practice.pairs
    }
    index = _build_index(repository, "new_or_deleted_text")
    retrieval = {}
    for amendment_id in sorted(amendments):
        text = repository.amendments[amendment_id].text_in("en")
        if text is None:
            raise ValueError(f"English amendment missing: {amendment_id}")
        shortlist = index.search(amendment_id, text.old, text.new, k=len(proposals))
        retrieval[amendment_id] = [
            {"proposal_id": item.passage.document_id, "rank": item.rank, "score": item.score}
            for item in shortlist.candidates
        ]
    pairs = [
        {
            "candidate_id": item.pair.candidate_id,
            "amendment_id": item.pair.amendment_id,
            "proposal_id": item.pair.proposal_id,
            "amendment_key": amendments[item.pair.amendment_id],
            "submission_key": delta(item.pair.submission.old, item.pair.submission.new, "passage"),
            "amendment_full_key": add("query", item.pair.amendment.new),
            "submission_full_key": add("passage", item.pair.submission.new),
        }
        for item in practice.pairs
    ]
    source_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.glob("*.json"))
    }
    write_json(
        output / "inputs.json",
        {
            "schema": "embedding-inputs-1",
            "source_hashes": source_hashes,
            "representation": (
                "Main changed_spans token diff; each run INSERT: or DELETE: plus exact text. "
                "No-change keys are null; full-text diagnostic keys retained."
            ),
            "bm25": retrieval,
            "corpus": "new_or_deleted_text",
            "texts": texts,
            "proposals": proposals,
            "amendments": [{"id": key, "key": value} for key, value in sorted(amendments.items())],
            "pairs": pairs,
        },
    )
    write_json(
        output / "labels.json",
        {
            "schema": "lobbyplag-labels-1",
            "source_hashes": source_hashes,
            "label_rule": (
                "Existing build_practice_set; historical volunteer verified positives "
                "and crowd rejected weak negatives."
            ),
            "pairs": [
                {
                    "candidate_id": item.pair.candidate_id,
                    "amendment_id": item.pair.amendment_id,
                    "proposal_id": item.pair.proposal_id,
                    "positive": item.influenced,
                    "organization_id": item.pair.organization_id,
                }
                for item in practice.pairs
            ],
        },
    )
    print(
        {
            "texts": len(texts),
            "proposals": len(proposals),
            "queries": len(amendments),
            "pairs": len(pairs),
            "positives": sum(item.influenced for item in practice.pairs),
        },
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.data, args.out)
