"""Measure a fused retriever and the shortlist's precision and cost on LobbyPlag (`rev-00x6`).

PR #35 found that searching an amendment's changed words (delta) and searching its whole
text miss different true sources, and that the plan asks for several retrievers fused. This
measures four shortlists on the same verified pairs and the same deletion-aware corpus:

* delta: the changed words only;
* whole_text: the whole proposed text;
* rrf: reciprocal-rank fusion of the two (a rank-based merge, constant 60);
* union: the top k of each, without ranking across them.

For each it reports recall@k, the smallest per-retriever k that reaches the target recall (a
runtime candidate cap, to be set from this and recorded in the run manifest), the shortlist
size that cap implies, and how the shortlist splits into verified, weakly rejected and
unlabelled proposals. Run from the repository root:

    uv run --directory backend --locked python -m influence.practice.fused \
        --data /absolute/path/to/data/lobbyplag --out evaluation/fused-retrieval.json

The JSON is a pure function of the input files: it records their SHA-256 digests and no
timing, which is printed instead. Every candidate was first proposed by LobbyPlag's own
matcher, so recall is optimistic for real submissions, and LobbyPlag's negatives are weak:
volunteers rejected them, nobody confirmed they are wrong, and the many proposals no
volunteer ever looked at are unlabelled, not negative (bead R1).
"""

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from influence.practice.__main__ import DATA_FILES
from influence.practice.harness import write_atomically
from influence.practice.labels import PracticeDataError, PracticeSet, build_practice_set
from influence.practice.recall import VerifiedPair, build_index
from influence.repositories.lobbyplag import (
    DatasetInvalidError,
    DatasetUnavailableError,
    DemoRepository,
)
from influence.services.retrieval import PassageIndex, fuse_rankings

KS = (5, 10, 20, 40, 50)
PRECISION_KS = (20, 40)
DEPTH = 100
RRF_CONSTANT = 60
TARGET_RECALL = 0.95
type Retriever = Literal["delta", "whole_text", "rrf", "union"]
type Subset = Literal["all_verified_pairs", "amendment_has_new_text"]
RETRIEVERS: tuple[Retriever, ...] = ("delta", "whole_text", "rrf", "union")

CAVEATS = (
    "Every candidate was first proposed by LobbyPlag's own lexical matcher, so verified pairs "
    "are lexically similar by construction; recall on real submissions can be lower.",
    "One law (GDPR, 2013) and a pool of about 1,000 proposals; recall falls as the pool grows.",
    "Weak negatives are proposals volunteers checked and never voted a copy; nobody confirmed "
    "they are wrong. Most shortlist members are unlabelled, which is not the same as wrong, so "
    "labelled precision describes only the labelled share of the shortlist.",
    "An amendment with no new wording cannot be searched by its whole text. On the full set "
    "the whole_text row counts those as misses, and rrf and union fall back to delta alone.",
)


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FusedRow(Frozen):
    subset: Subset
    retriever: Retriever
    pairs: int
    recall_at: dict[str, float]
    mrr: float | None
    # Smallest per-retriever k at which recall reaches TARGET_RECALL, or None within DEPTH.
    cap_for_target: int | None
    recall_at_depth: float
    # Mean number of distinct proposals returned per amendment at each k.
    mean_shortlist_size_at: dict[str, float]
    mean_shortlist_size_at_cap: float | None


class PrecisionRow(Frozen):
    retriever: Retriever
    k: int
    amendments: int
    mean_candidates: float
    mean_verified: float
    mean_weakly_rejected: float
    mean_unlabelled: float
    # Verified share of the labelled candidates only; None when none were labelled.
    labelled_precision: float | None


class FusedReport(Frozen):
    kind: Literal["fused-retrieval-v1"]
    input_sha256: dict[str, str]
    verified_pairs: int
    amendments: int
    amendments_without_whole_text: int
    corpus_passages: int
    depth: int
    rrf_constant: int
    target_recall: float
    rows: tuple[FusedRow, ...]
    precision: tuple[PrecisionRow, ...]
    caveats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Rankings:
    """The ranked proposal IDs each query returned for one amendment; empty if it cannot run."""

    delta: list[str]
    whole_text: list[str]
    fused: list[str]


def _shortlist(retriever: Retriever, rankings: _Rankings, k: int) -> list[str]:
    if retriever == "delta":
        return rankings.delta[:k]
    if retriever == "whole_text":
        return rankings.whole_text[:k]
    if retriever == "rrf":
        return rankings.fused[:k]
    head = rankings.delta[:k]
    return head + [item for item in rankings.whole_text[:k] if item not in head]


def _search(
    index: PassageIndex, pair: VerifiedPair, kind: Literal["delta", "whole_text"]
) -> list[str]:
    old = pair.amendment.old if kind == "delta" else None
    try:
        shortlist = index.search(pair.amendment_id, old, pair.amendment.new, k=DEPTH)
    except ValueError:
        return []
    return [item.passage.document_id for item in shortlist.candidates]


def _recall_and_cap(
    retriever: Retriever, pairs: Sequence[VerifiedPair], rankings: Mapping[str, _Rankings]
) -> tuple[dict[str, float], float | None, int | None, float, dict[str, float], float | None]:
    """Recall at each k, MRR, the cap reaching the target, recall at depth, mean sizes."""

    def found(k: int) -> float:
        hits = sum(
            p.proposal_id in _shortlist(retriever, rankings[p.amendment_id], k) for p in pairs
        )
        return hits / len(pairs)

    def size(k: int) -> float:
        amendments = {pair.amendment_id for pair in pairs}
        total = sum(len(_shortlist(retriever, rankings[a], k)) for a in amendments)
        return total / len(amendments)

    mrr: float | None = None
    if retriever != "union":
        ranks = [
            _shortlist(retriever, rankings[p.amendment_id], DEPTH).index(p.proposal_id) + 1
            for p in pairs
            if p.proposal_id in _shortlist(retriever, rankings[p.amendment_id], DEPTH)
        ]
        mrr = sum(1 / rank for rank in ranks) / len(pairs)
    cap = next((k for k in range(1, DEPTH + 1) if found(k) >= TARGET_RECALL), None)
    return (
        {str(k): found(k) for k in KS},
        mrr,
        cap,
        found(DEPTH),
        {str(k): size(k) for k in KS},
        size(cap) if cap is not None else None,
    )


def _precision(
    retriever: Retriever,
    k: int,
    amendment_ids: Sequence[str],
    rankings: Mapping[str, _Rankings],
    labels: Mapping[tuple[str, str], bool],
) -> PrecisionRow:
    verified = weak = unlabelled = candidates = 0
    for amendment_id in amendment_ids:
        for proposal_id in _shortlist(retriever, rankings[amendment_id], k):
            candidates += 1
            label = labels.get((amendment_id, proposal_id))
            if label is None:
                unlabelled += 1
            elif label:
                verified += 1
            else:
                weak += 1
    count = len(amendment_ids)
    return PrecisionRow(
        retriever=retriever,
        k=k,
        amendments=count,
        mean_candidates=candidates / count,
        mean_verified=verified / count,
        mean_weakly_rejected=weak / count,
        mean_unlabelled=unlabelled / count,
        labelled_precision=verified / (verified + weak) if verified + weak else None,
    )


def measure_fused(
    repository: DemoRepository, practice: PracticeSet, input_sha256: dict[str, str]
) -> tuple[FusedReport, dict[str, float]]:
    """Recall, cap, precision and cost of each retriever over every verified pair.

    One delta search and one whole-text search per verified amendment, to depth 100, then
    every shortlist is a slice or a merge of those lists. Returns the deterministic report
    and, separately, the mean seconds per query (not part of the report).
    """
    verified = [item for item in practice.pairs if item.influenced]
    if not verified:
        raise PracticeDataError("No verified pairs to measure retrieval on")
    pairs = [
        VerifiedPair(item.pair.amendment_id, item.pair.amendment, item.pair.proposal_id)
        for item in verified
    ]
    labels = {(i.pair.amendment_id, i.pair.proposal_id): i.influenced for i in practice.pairs}
    index = build_index(repository, "new_or_deleted_text")
    first = {pair.amendment_id: pair for pair in reversed(pairs)}
    seconds = {"delta": 0.0, "whole_text": 0.0, "rrf": 0.0}
    rankings: dict[str, _Rankings] = {}
    for amendment_id, pair in sorted(first.items()):
        started = perf_counter()
        delta = _search(index, pair, "delta")
        seconds["delta"] += perf_counter() - started
        started = perf_counter()
        whole = _search(index, pair, "whole_text")
        seconds["whole_text"] += perf_counter() - started
        started = perf_counter()
        fused = fuse_rankings([ranking for ranking in (delta, whole) if ranking], RRF_CONSTANT)
        seconds["rrf"] += perf_counter() - started
        rankings[amendment_id] = _Rankings(delta, whole, fused)
    with_text = [pair for pair in pairs if pair.amendment.new.strip()]
    rows: list[FusedRow] = []
    for subset, chosen in (
        ("all_verified_pairs", pairs),
        ("amendment_has_new_text", with_text),
    ):
        for retriever in RETRIEVERS:
            recall, mrr, cap, deep, sizes, cap_size = _recall_and_cap(retriever, chosen, rankings)
            rows.append(
                FusedRow(
                    subset=cast("Subset", subset),
                    retriever=retriever,
                    pairs=len(chosen),
                    recall_at=recall,
                    mrr=mrr,
                    cap_for_target=cap,
                    recall_at_depth=deep,
                    mean_shortlist_size_at=sizes,
                    mean_shortlist_size_at_cap=cap_size,
                )
            )
    amendment_ids = sorted(rankings)
    precision = tuple(
        _precision(retriever, k, amendment_ids, rankings, labels)
        for retriever in RETRIEVERS
        for k in PRECISION_KS
    )
    report = FusedReport(
        kind="fused-retrieval-v1",
        input_sha256=input_sha256,
        verified_pairs=len(pairs),
        amendments=len(rankings),
        amendments_without_whole_text=sum(not r.whole_text for r in rankings.values()),
        corpus_passages=len(index),
        depth=DEPTH,
        rrf_constant=RRF_CONSTANT,
        target_recall=TARGET_RECALL,
        rows=tuple(rows),
        precision=precision,
        caveats=CAVEATS,
    )
    count = len(rankings)
    return report, {name: total / count for name, total in seconds.items()}


def render(report: FusedReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m influence.practice.fused",
        description="Measure fused retrieval, shortlist precision and cap on LobbyPlag.",
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
        report, seconds = measure_fused(repository, build_practice_set(repository), hashes)
    except (OSError, DatasetUnavailableError, DatasetInvalidError, PracticeDataError) as error:
        cause = f" ({error.__cause__})" if error.__cause__ else ""
        print(f"error: {error}{cause}", file=sys.stderr)
        return 1
    write_atomically(out, render(report))
    print(f"{report.verified_pairs} verified pairs, {report.amendments} amendments")
    print(
        f"{'subset':<24}{'retriever':<12}{'pairs':>6}" + "".join(f"{'@' + str(k):>8}" for k in KS)
    )
    print(f"{'':<42}{'cap@.95':>9}{'size@cap':>10}")
    for row in report.rows:
        recalls = "".join(f"{row.recall_at[str(k)]:>8.3f}" for k in KS)
        cap = "none" if row.cap_for_target is None else str(row.cap_for_target)
        size = (
            "-"
            if row.mean_shortlist_size_at_cap is None
            else f"{row.mean_shortlist_size_at_cap:.1f}"
        )
        print(
            f"{row.subset:<24}{row.retriever:<12}{row.pairs:>6}{recalls}"
            f"  cap {cap:>4} size {size:>6}"
        )
    for item in report.precision:
        share = "n/a" if item.labelled_precision is None else f"{item.labelled_precision:.3f}"
        print(
            f"{item.retriever:<12}@{item.k:<3} candidates {item.mean_candidates:5.1f}  "
            f"verified {item.mean_verified:.2f}  weak-rejected {item.mean_weakly_rejected:.2f}  "
            f"unlabelled {item.mean_unlabelled:5.1f}  labelled precision {share}"
        )
    per_query = ", ".join(f"{name} {value * 1000:.2f} ms" for name, value in seconds.items())
    print(f"Wrote {out}. Mean per query: {per_query}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
