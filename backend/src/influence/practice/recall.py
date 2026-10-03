"""Measure candidate-retrieval recall on LobbyPlag's volunteer-verified pairs (`rev-00x6`).

Retrieval only narrows the search, so what it must not do is lose the true source. For each
verified (amendment, proposal) pair this asks: is the proposal among the top k passages the
BM25 index returns for the amendment? That is recall@k, measured before any scoring.

Two choices are compared on the same queries, so each difference is a difference in the
method and not in the sample (AGENTS.md: report before and after on the same data):

* corpus: a proposal is indexed by its new wording only, or by its new wording and, when it
  only deletes, by the wording it deletes;
* query: the amendment's changed words (delta) or its whole proposed text.

Run from the repository root:

    uv run --directory backend --locked python -m influence.practice.recall \
        --data /absolute/path/to/data/lobbyplag --out evaluation/retrieval-recall.json

The JSON is a pure function of the input files: it records their SHA-256 digests, no timing.
Every candidate here was first proposed by LobbyPlag's own matcher, so the pairs are
lexically similar by construction and recall is optimistic for real submissions.
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from influence.practice.__main__ import DATA_FILES
from influence.practice.harness import write_atomically
from influence.practice.labels import PracticeDataError, PracticeSet, build_practice_set
from influence.repositories.lobbyplag import (
    DatasetInvalidError,
    DatasetUnavailableError,
    DemoRepository,
    RawText,
)
from influence.schemas.retrieval import SourcePassage
from influence.services.retrieval import PassageIndex

KS = (5, 10, 20, 50)
type Corpus = Literal["new_text_only", "new_or_deleted_text"]
type Query = Literal["delta", "whole_text"]
type Subset = Literal["all_verified_pairs", "amendment_has_new_text"]

CAVEATS = (
    "Every candidate was first proposed by LobbyPlag's own lexical matcher, so verified pairs "
    "are lexically similar by construction; recall on real submissions can be lower.",
    "The pool is one law (GDPR, 2013) and 1,159 proposals; recall falls as the pool grows.",
    "A query that cannot be run (over-long text) counts as a miss and is listed in `query_errors`.",
)


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RecallRow(Frozen):
    corpus: Corpus
    query: Query
    subset: Subset
    pairs: int
    query_errors: int
    recall_at: dict[str, float]
    mrr: float


class RecallReport(Frozen):
    kind: Literal["retrieval-recall-v1"]
    input_sha256: dict[str, str]
    verified_pairs: int
    corpus_passages: dict[str, int]
    proposals_with_no_text: int
    chance_recall_at: dict[str, float]
    rows: tuple[RecallRow, ...]
    caveats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerifiedPair:
    amendment_id: str
    amendment: RawText
    proposal_id: str


def _passage_text(proposal: RawText, corpus: Corpus) -> str:
    if proposal.new.strip() or corpus == "new_text_only":
        return proposal.new
    return proposal.old


def build_index(repository: DemoRepository, corpus: Corpus) -> PassageIndex:
    passages = tuple(
        SourcePassage(document_id=uid, start=0, end=len(text), text=text)
        for uid, proposal in sorted(repository.proposals.items())
        if (text := _passage_text(proposal.text, corpus)).strip()
    )
    return PassageIndex(passages)


def _evaluate(
    index: PassageIndex, pairs: Sequence[VerifiedPair], query: Query
) -> tuple[dict[str, float], float, int]:
    """Recall@k and mean reciprocal rank over `pairs`, one search per distinct amendment."""
    ranked: dict[str, list[str] | None] = {}
    for pair in pairs:
        if pair.amendment_id in ranked:
            continue
        old = pair.amendment.old if query == "delta" else None
        try:
            shortlist = index.search(pair.amendment_id, old, pair.amendment.new, k=max(KS))
        except ValueError:
            ranked[pair.amendment_id] = None
            continue
        ranked[pair.amendment_id] = [item.passage.document_id for item in shortlist.candidates]
    hits = dict.fromkeys(KS, 0)
    reciprocal = 0.0
    for pair in pairs:
        order = ranked[pair.amendment_id] or []
        if pair.proposal_id in order:
            rank = order.index(pair.proposal_id) + 1
            reciprocal += 1 / rank
            for k in KS:
                hits[k] += rank <= k
    errors = sum(1 for pair in pairs if ranked[pair.amendment_id] is None)
    total = len(pairs)
    return (
        {str(k): hits[k] / total for k in KS},
        reciprocal / total,
        errors,
    )


def measure_recall(
    repository: DemoRepository, practice: PracticeSet, input_sha256: dict[str, str]
) -> RecallReport:
    """Recall of BM25 retrieval on every verified pair, for each corpus and query choice.

    Builds two indexes in linear time and issues one search per verified amendment and
    configuration; 144 amendments and 1,159 proposals run in about a second.
    """
    pairs = [
        VerifiedPair(item.pair.amendment_id, item.pair.amendment, item.pair.proposal_id)
        for item in practice.pairs
        if item.influenced
    ]
    if not pairs:
        raise PracticeDataError("No verified pairs to measure retrieval on")
    with_text = [pair for pair in pairs if pair.amendment.new.strip()]
    indexes: dict[Corpus, PassageIndex] = {
        "new_text_only": build_index(repository, "new_text_only"),
        "new_or_deleted_text": build_index(repository, "new_or_deleted_text"),
    }
    sizes = {name: len(index) for name, index in indexes.items()}
    queries: tuple[Query, ...] = ("delta", "whole_text")
    plan: list[tuple[Corpus, Query, Subset, list[VerifiedPair]]] = [
        (corpus, "delta", "all_verified_pairs", pairs) for corpus in indexes
    ]
    plan.extend(
        (corpus, query, "amendment_has_new_text", with_text)
        for corpus in indexes
        for query in queries
    )
    rows: list[RecallRow] = []
    for corpus, query, subset, chosen in plan:
        recall, mrr, errors = _evaluate(indexes[corpus], chosen, query)
        rows.append(
            RecallRow(
                corpus=corpus,
                query=query,
                subset=subset,
                pairs=len(chosen),
                query_errors=errors,
                recall_at=recall,
                mrr=mrr,
            )
        )
    pool = sizes["new_or_deleted_text"]
    return RecallReport(
        kind="retrieval-recall-v1",
        input_sha256=input_sha256,
        verified_pairs=len(pairs),
        corpus_passages=sizes,
        proposals_with_no_text=len(repository.proposals) - pool,
        chance_recall_at={str(k): min(1.0, k / pool) for k in KS},
        rows=tuple(rows),
        caveats=CAVEATS,
    )


def render(report: RecallReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m influence.practice.recall",
        description="Measure BM25 candidate-retrieval recall on LobbyPlag's verified pairs.",
    )
    parser.add_argument("--data", type=Path, required=True, help="LobbyPlag snapshot directory")
    parser.add_argument("--out", type=Path, required=True, help="Results JSON to (re)write")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    data, out = cast("Path", args.data), cast("Path", args.out)
    if not out.parent.is_dir():
        parser.error(f"output directory does not exist: {out.parent}")
    try:
        repository = DemoRepository.load(data)
        hashes = {f"{name}.json": _sha256(data / f"{name}.json") for name in DATA_FILES}
        report = measure_recall(repository, build_practice_set(repository), hashes)
    except (OSError, DatasetUnavailableError, DatasetInvalidError, PracticeDataError) as error:
        cause = f" ({error.__cause__})" if error.__cause__ else ""
        print(f"error: {error}{cause}", file=sys.stderr)
        return 1
    write_atomically(out, render(report))
    chance = report.chance_recall_at["20"]
    print(f"{report.verified_pairs} verified pairs; chance recall@20 {chance:.3f}")
    header = f"{'corpus':<22}{'query':<12}{'subset':<26}{'pairs':>6}"
    print(header + "".join(f"{'@' + str(k):>8}" for k in KS) + f"{'MRR':>8}")
    for row in report.rows:
        recalls = "".join(f"{row.recall_at[str(k)]:>8.3f}" for k in KS)
        print(
            f"{row.corpus:<22}{row.query:<12}{row.subset:<26}{row.pairs:>6}{recalls}{row.mrr:>8.3f}"
        )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
