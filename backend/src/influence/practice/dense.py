"""Measure the Qwen meaning signals on LobbyPlag's labelled pairs, beside BM25 and the edit scorer.

Three questions, answered on the same pairs so a difference is the method's:

1. Retrieval. For each of the 172 volunteer-verified (amendment, proposal) pairs, is the
   proposal among the top k passages? Compared: BM25 on the amendment's changed words (delta)
   and on its whole text, the dense retriever on the same two queries, and the union of
   shortlists (top k from each retriever), which is what a runtime would send on to scoring.
2. Scoring. The practice harness's folds, seed and simulated tests, with the proposal read as
   prose (its original unknown): the embedding cosine of the amendment's changed words and the
   proposal text, and the reranker's probability that the passage asks for the amendment's
   change, against the edit scorer on clean old and new wording (`lexical-delta-v1`) and
   against the edit scorer's overlap on prose (`prose-dice`, what the assessor computed).
3. A threshold. Whether the judge's probability separates verified positives from weak
   negatives well enough to publish on, by the rule of `practice/calibrate.py`: the least
   threshold whose Wilson 95% lower bound on precision clears a floor, chosen on the
   even-numbered folds and then read on the odd ones, which played no part in choosing it.
   And a funnel: how much an embedding cut would spare the slow judge, and what it would cost.

Run from the repository root, after `make fetch-lobbyplag`, `make fetch-qwen-embedding` and
`make fetch-qwen-reranker`:

    uv run --directory backend --locked --group models python -m influence.practice.dense \
        --data /path/to/data/lobbyplag --model /path/to/data/models/qwen3-embedding-0.6b \
        --reranker /path/to/data/models/qwen3-reranker-0.6b --out evaluation/dense-meaning.json

The JSON is a pure function of the input files, the model files and the options: it records
their SHA-256 digests and no timing, and floats are rounded to six places. Timing is printed.
Every candidate here was first proposed by LobbyPlag's own lexical matcher, so the pairs are
lexically similar by construction; this favours BM25 and says little about paraphrase.
"""

import argparse
import hashlib
import json
import platform
import statistics
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from influence.practice.__main__ import DATA_FILES, PER_CLASS, TOP_K, lexical_scores
from influence.practice.calibrate import (
    COPIED_FLOOR,
    MIN_PAIRS,
    REWORDED_FLOOR,
    TABLE_THRESHOLDS,
    Counts,
    ThresholdRow,
    choose_threshold,
    counts,
)
from influence.practice.folds import FoldPlan, make_folds
from influence.practice.harness import (
    SimulationSettings,
    evaluate,
    out_of_fold_scores,
    simulated_tests,
    write_atomically,
)
from influence.practice.labels import (
    LabelledPair,
    PracticeDataError,
    PracticePair,
    PracticeSet,
    build_practice_set,
)
from influence.practice.recall import KS
from influence.repositories.lobbyplag import (
    DatasetInvalidError,
    DatasetUnavailableError,
    DemoRepository,
)
from influence.schemas.retrieval import SourcePassage
from influence.schemas.scoring import ScoreRequest, TextChange
from influence.services.embedding import (
    DenseIndex,
    EmbeddingCache,
    EmbedFunction,
    cosine,
    delta_text,
    embed_texts,
    with_instruction,
)
from influence.services.judge import ScoreFunction, judge_pairs
from influence.services.qwen_onnx import BATCH_SIZE, MODEL_ID, QwenError, load_qwen
from influence.services.qwen_reranker import MODEL_ID as RERANKER_ID
from influence.services.qwen_reranker import load_reranker
from influence.services.retrieval import PassageIndex
from influence.services.scoring import score_pair

SEED = 0
DRAWS = 2000
FOLDS = 5
RECALL_THRESHOLD = 0.5
UNION_KS = (5, 10, 20)
ROUND = 6
EMBEDDING_FILES = ("onnx/model_int8.onnx", "tokenizer.json")
RERANKER_FILES = ("model.onnx", "tokenizer.json")
FUNNEL_CUTS = (0.5, 0.6, 0.7, 0.8)
type Ranking = dict[str, list[str] | None]
type Scorer = Callable[[Sequence[LabelledPair], Sequence[PracticePair]], list[float]]
type EmbedLoader = Callable[[Path], EmbedFunction]
type JudgeLoader = Callable[[Path], ScoreFunction]

CAVEATS = (
    "Every candidate was first proposed by LobbyPlag's own lexical matcher, so verified pairs "
    "are lexically similar by construction; this favours BM25 and understates what a meaning "
    "signal adds for paraphrase.",
    "One law (GDPR, 2013) and a pool of about 1,000 proposals; recall falls as the pool grows.",
    "LobbyPlag proposals are short edits. The meaning scorers read only a proposal's new wording "
    "(its deleted wording when it only deletes), as if it were a passage quoted from a paper.",
    "Negatives are weak: crowd-rejected candidates only; unlabelled candidates are not negatives "
    "(bead R1). Positives are mostly verbatim copies, so precision on rewordings is unmeasured.",
    "Embeddings are 8-bit and computed one text per call, since this build's vectors depend on "
    "the batch (see services/qwen_onnx.py).",
    "A query that cannot run (empty or over-long text) counts as a miss and is listed in "
    "`query_errors`.",
)


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RetrievalRow(Frozen):
    config: str
    kind: Literal["ranking", "union"]
    pairs: int
    query_errors: int
    # For a ranking, the pair's rank cut-off; for a union, the cut-off taken from each list.
    recall_at: dict[str, float]
    mrr: float | None
    candidates_at: dict[str, float] | None


class ScorerRow(Frozen):
    scorer: str
    description: str
    auc_mean: float
    auc_p10: float
    precision_at_top_mean: float
    precision_at_top_p10: float
    recall_mean: float
    recall_p10: float
    full_set_auc: float


class Separation(Frozen):
    """How far the judge's probability sits between verified positives and weak negatives."""

    positives: int
    negatives: int
    positives_mean: float
    negatives_mean: float
    positives_median: float
    negatives_median: float


class JudgeProposal(Frozen):
    tier: Literal["copied", "reworded"]
    floor: float
    min_pairs: int
    threshold: float | None
    development: Counts | None
    held_out: Counts | None


class FunnelRow(Frozen):
    """What keeping only pairs whose embedding cosine is at least `cosine_at_least` leaves."""

    cosine_at_least: float
    positives_kept: float
    negatives_kept: float
    pairs_kept: float


class JudgeReport(Frozen):
    scorer: str
    reranker_id: str
    reranker_sha256: dict[str, str]
    separation: Separation
    table: tuple[ThresholdRow, ...]
    proposals: tuple[JudgeProposal, ...]
    development_folds: tuple[int, ...]
    held_out_folds: tuple[int, ...]


class DenseReport(Frozen):
    kind: Literal["dense-meaning-v1"]
    model_id: str
    input_sha256: dict[str, str]
    model_sha256: dict[str, str]
    verified_pairs: int
    labelled_pairs: int
    corpus_passages: int
    retrieval: tuple[RetrievalRow, ...]
    scorers: tuple[ScorerRow, ...]
    funnel: tuple[FunnelRow, ...]
    judges: tuple[JudgeReport, ...]
    caveats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Pair:
    amendment_id: str
    old: str
    new: str
    proposal_id: str


@dataclass(frozen=True, slots=True)
class Measured:
    """The scorers' table, and each scorer's out-of-fold scores for later analysis."""

    rows: tuple[ScorerRow, ...]
    scores: dict[str, tuple[float, ...]]


def _proposal_text(old: str, new: str) -> str:
    """A proposal as searchable text: its new wording, else the wording it deletes."""
    return new if new.strip() else old


def _rounded(value: float) -> float:
    return round(value, ROUND)


def _delta_or_none(old: str, new: str) -> str | None:
    try:
        text = delta_text(old, new)
    except ValueError:
        return None
    return text if text.strip() else None


def _bm25_ranking(index: PassageIndex, pairs: Sequence[_Pair], *, delta: bool) -> Ranking:
    ranked: Ranking = {}
    for pair in pairs:
        if pair.amendment_id in ranked:
            continue
        try:
            shortlist = index.search(
                pair.amendment_id, pair.old if delta else None, pair.new, k=max(KS)
            )
        except ValueError:
            ranked[pair.amendment_id] = None
        else:
            ranked[pair.amendment_id] = [item.passage.document_id for item in shortlist.candidates]
    return ranked


def _dense_ranking(index: DenseIndex, pairs: Sequence[_Pair], *, delta: bool) -> Ranking:
    ranked: Ranking = {}
    for pair in pairs:
        if pair.amendment_id in ranked:
            continue
        query = _delta_or_none(pair.old, pair.new) if delta else pair.new
        if query is None or not query.strip():
            ranked[pair.amendment_id] = None
        else:
            hits = index.search(query, k=max(KS))
            ranked[pair.amendment_id] = [hit.passage.document_id for hit in hits]
    return ranked


def _ranking_row(config: str, pairs: Sequence[_Pair], ranked: Ranking) -> RetrievalRow:
    hits = dict.fromkeys(KS, 0)
    reciprocal = 0.0
    for pair in pairs:
        order = ranked[pair.amendment_id] or []
        if pair.proposal_id in order:
            rank = order.index(pair.proposal_id) + 1
            reciprocal += 1 / rank
            for k in KS:
                hits[k] += rank <= k
    total = len(pairs)
    return RetrievalRow(
        config=config,
        kind="ranking",
        pairs=total,
        query_errors=sum(1 for pair in pairs if ranked[pair.amendment_id] is None),
        recall_at={str(k): _rounded(hits[k] / total) for k in KS},
        mrr=_rounded(reciprocal / total),
        candidates_at=None,
    )


def _union_row(config: str, pairs: Sequence[_Pair], lists: Sequence[Ranking]) -> RetrievalRow:
    amendments = list(dict.fromkeys(pair.amendment_id for pair in pairs))
    hits = dict.fromkeys(UNION_KS, 0)
    sizes = dict.fromkeys(UNION_KS, 0)
    for k in UNION_KS:
        pooled = {
            amendment: {doc for ranked in lists for doc in (ranked[amendment] or [])[:k]}
            for amendment in amendments
        }
        sizes[k] = sum(len(found) for found in pooled.values())
        hits[k] = sum(pair.proposal_id in pooled[pair.amendment_id] for pair in pairs)
    return RetrievalRow(
        config=config,
        kind="union",
        pairs=len(pairs),
        query_errors=sum(
            1 for pair in pairs if all(ranked[pair.amendment_id] is None for ranked in lists)
        ),
        recall_at={str(k): _rounded(hits[k] / len(pairs)) for k in UNION_KS},
        mrr=None,
        candidates_at={str(k): _rounded(sizes[k] / len(amendments)) for k in UNION_KS},
    )


def measure_retrieval(
    repository: DemoRepository,
    practice: PracticeSet,
    embed: EmbedFunction,
    *,
    model_id: str,
    cache: EmbeddingCache | None,
    batch_size: int = BATCH_SIZE,
) -> tuple[tuple[RetrievalRow, ...], int, int]:
    """Recall of BM25, dense and their union; also the verified pair and passage counts."""
    pairs = [
        _Pair(
            item.pair.amendment_id,
            item.pair.amendment.old,
            item.pair.amendment.new,
            item.pair.proposal_id,
        )
        for item in practice.pairs
        if item.influenced
    ]
    if not pairs:
        raise PracticeDataError("No verified pairs to measure retrieval on")
    passages = tuple(
        SourcePassage(document_id=uid, start=0, end=len(text), text=text)
        for uid, proposal in sorted(repository.proposals.items())
        if (text := _proposal_text(proposal.text.old, proposal.text.new)).strip()
    )
    bm25 = PassageIndex(passages)
    dense = DenseIndex(passages, embed, model_id=model_id, cache=cache, batch_size=batch_size)
    bm25_delta = _bm25_ranking(bm25, pairs, delta=True)
    bm25_whole = _bm25_ranking(bm25, pairs, delta=False)
    dense_delta = _dense_ranking(dense, pairs, delta=True)
    dense_whole = _dense_ranking(dense, pairs, delta=False)
    rows = (
        _ranking_row("bm25 delta", pairs, bm25_delta),
        _ranking_row("bm25 whole text", pairs, bm25_whole),
        _ranking_row("dense delta", pairs, dense_delta),
        _ranking_row("dense whole text", pairs, dense_whole),
        _union_row("bm25 delta + bm25 whole", pairs, (bm25_delta, bm25_whole)),
        _union_row(
            "bm25 delta + bm25 whole + dense delta", pairs, (bm25_delta, bm25_whole, dense_delta)
        ),
        _union_row(
            "bm25 delta + bm25 whole + dense delta + dense whole",
            pairs,
            (bm25_delta, bm25_whole, dense_delta, dense_whole),
        ),
        _union_row("dense delta + dense whole", pairs, (dense_delta, dense_whole)),
    )
    return rows, len(pairs), len(passages)


def prose_dice_scores(
    _training: Sequence[LabelledPair], test: Sequence[PracticePair]
) -> list[float]:
    """The edit scorer with the proposal's text as an insertion; 0 where it cannot run."""
    scores: list[float] = []
    for pair in test:
        try:
            request = ScoreRequest(
                amendment=TextChange(old=pair.amendment.old, new=pair.amendment.new),
                submission=TextChange(
                    old="", new=_proposal_text(pair.submission.old, pair.submission.new)
                ),
            )
        except ValueError:
            scores.append(0.0)
        else:
            scores.append(score_pair(request).score)
    return scores


def cosine_scorer(
    embed: EmbedFunction,
    *,
    model_id: str,
    cache: EmbeddingCache | None,
    batch_size: int,
    whole: bool,
) -> Scorer:
    """Cosine of the amendment's changed words (or whole new text) and the proposal's text.

    Mapped from [-1, 1] to [0, 1] as the harness requires. Unsupervised: no label is read.
    """

    def scores(_training: Sequence[LabelledPair], test: Sequence[PracticePair]) -> list[float]:
        queries: list[str | None] = []
        for pair in test:
            text = (
                pair.amendment.new
                if whole
                else _delta_or_none(pair.amendment.old, pair.amendment.new)
            )
            queries.append(None if text is None or not text.strip() else with_instruction(text))
        documents = [_proposal_text(pair.submission.old, pair.submission.new) for pair in test]
        needed = list(
            dict.fromkeys(text for text in (*queries, *documents) if text and text.strip())
        )
        vectors = dict(
            zip(
                needed,
                embed_texts(needed, embed, model_id=model_id, cache=cache, batch_size=batch_size),
                strict=True,
            )
        )
        return [
            0.0
            if query is None or not document.strip()
            else (cosine(vectors[query], vectors[document]) + 1) / 2
            for query, document in zip(queries, documents, strict=True)
        ]

    return scores


def judge_scorer(
    score: ScoreFunction,
    *,
    model_id: str,
    cache: EmbeddingCache | None,
    batch_size: int,
    changes_only: bool = False,
) -> Scorer:
    """The reranker's probability that the proposal asks for the amendment's change.

    The amendment is shown as old -> new wording, or with `changes_only` as the words it adds
    and removes, and the proposal's new wording (the wording it deletes, if it only deletes) as
    the passage. Unsupervised: no label is read.
    """

    def scores(_training: Sequence[LabelledPair], test: Sequence[PracticePair]) -> list[float]:
        documents = [_proposal_text(pair.submission.old, pair.submission.new) for pair in test]
        chances = judge_pairs(
            [
                (pair.amendment.old, pair.amendment.new, document)
                for pair, document in zip(test, documents, strict=True)
                if document.strip()
            ],
            score,
            model_id=model_id,
            cache=cache,
            batch_size=batch_size,
            changes_only=changes_only,
        )
        found = iter(chances)
        return [next(found) if document.strip() else 0.0 for document in documents]

    return scores


def measure_scorers(
    practice: PracticeSet,
    embed: EmbedFunction,
    judge: ScoreFunction | None,
    *,
    model_id: str,
    judge_id: str = RERANKER_ID,
    cache: EmbeddingCache | None,
    batch_size: int = BATCH_SIZE,
) -> tuple[Measured, FoldPlan]:
    """The harness's folds, seed and simulated tests applied to each scorer in turn."""
    plan = make_folds(practice.pairs, FOLDS)
    tests = simulated_tests([item.influenced for item in practice.pairs], DRAWS, PER_CLASS, SEED)
    settings = SimulationSettings(
        draws=DRAWS,
        per_class=PER_CLASS,
        seed=SEED,
        generator="Python random.Random (Mersenne Twister)",
        top_k=TOP_K,
        recall_threshold=RECALL_THRESHOLD,
    )
    candidates: list[tuple[str, str, Scorer]] = [
        (
            "lexical-delta-v1",
            "The edit scorer on clean old and new wording, both originals known",
            lexical_scores,
        ),
        (
            "prose-dice",
            "The edit scorer with the proposal's text as an insertion, original unknown",
            prose_dice_scores,
        ),
        (
            "qwen-cosine-delta",
            "Cosine of the amendment's changed words and the proposal text",
            cosine_scorer(
                embed, model_id=model_id, cache=cache, batch_size=batch_size, whole=False
            ),
        ),
        (
            "qwen-cosine-whole",
            "Cosine of the amendment's whole new text and the proposal text",
            cosine_scorer(embed, model_id=model_id, cache=cache, batch_size=batch_size, whole=True),
        ),
    ]
    if judge is not None:
        candidates.extend(
            (
                (
                    "qwen-judge",
                    "The reranker's P(yes) that the proposal asks for the amendment's change, "
                    "the amendment shown as old -> new wording",
                    judge_scorer(judge, model_id=judge_id, cache=cache, batch_size=1),
                ),
                (
                    "qwen-judge-changes",
                    "The same question with the amendment shown only as the words it adds and "
                    "removes",
                    judge_scorer(
                        judge, model_id=judge_id, cache=cache, batch_size=1, changes_only=True
                    ),
                ),
            )
        )
    rows: list[ScorerRow] = []
    raw: dict[str, tuple[float, ...]] = {}
    for name, description, scorer in candidates:
        scores = out_of_fold_scores(scorer, practice.pairs, plan)
        raw[name] = tuple(scores)
        result = evaluate(description, scores, practice.pairs, plan, tests, settings)
        draws = result.draws
        rows.append(
            ScorerRow(
                scorer=name,
                description=description,
                auc_mean=_rounded(draws.auc.mean),
                auc_p10=_rounded(draws.auc.p10),
                precision_at_top_mean=_rounded(draws.precision_at_top.mean),
                precision_at_top_p10=_rounded(draws.precision_at_top.p10),
                recall_mean=_rounded(draws.recall.mean),
                recall_p10=_rounded(draws.recall.p10),
                full_set_auc=_rounded(result.full_set_auc),
            )
        )
    return Measured(tuple(rows), raw), plan


def funnel_table(scores: Sequence[float], labels: Sequence[bool]) -> tuple[FunnelRow, ...]:
    """Share of positives, negatives and all pairs kept by each cosine cut-off."""
    positives = sum(labels)
    negatives = len(labels) - positives
    rows: list[FunnelRow] = []
    for cut in FUNNEL_CUTS:
        kept = [label for score, label in zip(scores, labels, strict=True) if score >= cut]
        rows.append(
            FunnelRow(
                cosine_at_least=cut,
                positives_kept=_rounded(sum(kept) / positives),
                negatives_kept=_rounded((len(kept) - sum(kept)) / negatives),
                pairs_kept=_rounded(len(kept) / len(labels)),
            )
        )
    return tuple(rows)


def _split_folds(plan: FoldPlan) -> tuple[tuple[int, ...], tuple[int, ...], list[int], list[int]]:
    """Even-numbered folds develop the threshold; odd-numbered ones are read afterwards."""
    development_folds = tuple(n for n in range(len(plan.folds)) if n % 2 == 0)
    held_out_folds = tuple(n for n in range(len(plan.folds)) if n % 2 == 1)
    development = [i for n in development_folds for i in plan.folds[n].test]
    held_out = [i for n in held_out_folds for i in plan.folds[n].test]
    return development_folds, held_out_folds, development, held_out


def judge_report(
    scorer: str,
    scores: Sequence[float],
    practice: PracticeSet,
    plan: FoldPlan,
    reranker_sha256: dict[str, str],
) -> JudgeReport:
    """Separation, threshold table and the development-then-held-out threshold proposals."""
    labels = [item.influenced for item in practice.pairs]
    positives = [score for score, label in zip(scores, labels, strict=True) if label]
    negatives = [score for score, label in zip(scores, labels, strict=True) if not label]
    development_folds, held_out_folds, development, held_out = _split_folds(plan)
    table = tuple(
        ThresholdRow(
            threshold=threshold,
            all_pairs=counts(scores, labels, threshold),
            recall=round(sum(score >= threshold for score in positives) / len(positives), 4),
        )
        for threshold in TABLE_THRESHOLDS
    )

    def proposal(tier: Literal["copied", "reworded"], floor: float) -> JudgeProposal:
        def part(indices: Sequence[int]) -> tuple[list[float], list[bool]]:
            return [scores[i] for i in indices], [labels[i] for i in indices]

        threshold = choose_threshold(*part(development), floor)
        if threshold is None:
            return JudgeProposal(
                tier=tier,
                floor=floor,
                min_pairs=MIN_PAIRS,
                threshold=None,
                development=None,
                held_out=None,
            )
        return JudgeProposal(
            tier=tier,
            floor=floor,
            min_pairs=MIN_PAIRS,
            threshold=threshold,
            development=counts(*part(development), threshold),
            held_out=counts(*part(held_out), threshold),
        )

    return JudgeReport(
        scorer=scorer,
        reranker_id=RERANKER_ID,
        reranker_sha256=reranker_sha256,
        separation=Separation(
            positives=len(positives),
            negatives=len(negatives),
            positives_mean=_rounded(statistics.fmean(positives)),
            negatives_mean=_rounded(statistics.fmean(negatives)),
            positives_median=_rounded(statistics.median(positives)),
            negatives_median=_rounded(statistics.median(negatives)),
        ),
        table=table,
        proposals=(proposal("copied", COPIED_FLOOR), proposal("reworded", REWORDED_FLOOR)),
        development_folds=development_folds,
        held_out_folds=held_out_folds,
    )


def _sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _digests(directory: Path, names: Sequence[str]) -> dict[str, str]:
    return {name: _sha256(directory / name) for name in names if (directory / name).is_file()}


def render(report: DenseReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m influence.practice.dense",
        description="Measure the Qwen meaning signals on LobbyPlag's labelled pairs.",
    )
    parser.add_argument("--data", type=Path, required=True, help="LobbyPlag snapshot directory")
    parser.add_argument("--model", type=Path, required=True, help="Qwen3-Embedding files")
    parser.add_argument("--reranker", type=Path, default=None, help="Qwen3-Reranker files")
    parser.add_argument("--out", type=Path, required=True, help="Results JSON to (re)write")
    parser.add_argument("--cache", type=Path, default=None, help="Cache of vectors and scores")
    return parser


def print_report(report: DenseReport, timings: str) -> None:
    print(
        f"{report.verified_pairs} verified pairs, {report.corpus_passages} passages in the pool, "
        f"{report.labelled_pairs} labelled"
    )
    print(f"{'retrieval':<56}" + "".join(f"{'@' + str(k):>8}" for k in KS) + f"{'MRR':>8}")
    for row in report.retrieval:
        keys = KS if row.kind == "ranking" else UNION_KS
        recalls = "".join(f"{row.recall_at[str(k)]:>8.3f}" for k in keys)
        tail = f"{row.mrr:>8.3f}" if row.mrr is not None else ""
        extra = ""
        if row.candidates_at is not None:
            extra = "  candidates " + "/".join(f"{row.candidates_at[str(k)]:.0f}" for k in UNION_KS)
        print(f"{row.config + ' [' + row.kind + ']':<56}{recalls}{tail}{extra}")
    print(f"{'scorer':<22}{'AUC':>8}{'p10':>8}{'P@20':>8}{'p10':>8}{'recall':>8}{'p10':>8}")
    for scorer in report.scorers:
        print(
            f"{scorer.scorer:<22}{scorer.auc_mean:>8.3f}{scorer.auc_p10:>8.3f}"
            f"{scorer.precision_at_top_mean:>8.3f}{scorer.precision_at_top_p10:>8.3f}"
            f"{scorer.recall_mean:>8.3f}{scorer.recall_p10:>8.3f}"
        )
    print("funnel (cosine cut -> positives / negatives / all pairs kept):")
    for cut in report.funnel:
        print(
            f"  >= {cut.cosine_at_least:.1f}: {cut.positives_kept:.3f} / "
            f"{cut.negatives_kept:.3f} / {cut.pairs_kept:.3f}"
        )
    for judge in report.judges:
        sep = judge.separation
        print(
            f"{judge.scorer} P(yes): positives mean {sep.positives_mean:.3f} median "
            f"{sep.positives_median:.3f}; weak negatives mean {sep.negatives_mean:.3f} median "
            f"{sep.negatives_median:.3f}"
        )
        for found in judge.proposals:
            held = found.held_out
            text = (
                "no threshold reaches the floor"
                if found.threshold is None or held is None
                else (
                    f"threshold {found.threshold:.2f}; held-out {held.positives}/{held.pairs} "
                    f"(Wilson {held.wilson_low:.3f}-{held.wilson_high:.3f})"
                )
            )
            print(f"  {found.tier} (floor {found.floor:.2f}): {text}")
    print(timings)


def main(
    argv: Sequence[str] | None = None,
    load: EmbedLoader = load_qwen,
    load_judge: JudgeLoader = load_reranker,
) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    data, model, out = cast("Path", args.data), cast("Path", args.model), cast("Path", args.out)
    reranker = cast("Path | None", args.reranker)
    cache_path = cast("Path | None", args.cache)
    if not out.parent.is_dir():
        parser.error(f"output directory does not exist: {out.parent}")
    started = perf_counter()
    try:
        repository = DemoRepository.load(data)
        hashes = {f"{name}.json": _sha256(data / f"{name}.json") for name in DATA_FILES}
        practice = build_practice_set(repository)
        embed = load(model)
        judge = None if reranker is None else load_judge(reranker)
        loaded = perf_counter()
        cache = None if cache_path is None else EmbeddingCache(cache_path)
        rows, verified, passages = measure_retrieval(
            repository, practice, embed, model_id=MODEL_ID, cache=cache
        )
        retrieved = perf_counter()
        measured, plan = measure_scorers(practice, embed, judge, model_id=MODEL_ID, cache=cache)
    except (
        OSError,
        DatasetUnavailableError,
        DatasetInvalidError,
        PracticeDataError,
        QwenError,
    ) as error:
        cause = f" ({error.__cause__})" if error.__cause__ else ""
        print(f"error: {error}{cause}", file=sys.stderr)
        return 1
    labels = [item.influenced for item in practice.pairs]
    reranker_digests = {} if reranker is None else _digests(reranker, RERANKER_FILES)
    judged = tuple(
        judge_report(name, measured.scores[name], practice, plan, reranker_digests)
        for name in ("qwen-judge", "qwen-judge-changes")
        if name in measured.scores
    )
    report = DenseReport(
        kind="dense-meaning-v1",
        model_id=MODEL_ID,
        input_sha256=hashes,
        model_sha256=_digests(model, EMBEDDING_FILES),
        verified_pairs=verified,
        labelled_pairs=len(practice.pairs),
        corpus_passages=passages,
        retrieval=rows,
        scorers=measured.rows,
        funnel=funnel_table(measured.scores["qwen-cosine-delta"], labels),
        judges=judged,
        caveats=CAVEATS,
    )
    write_atomically(out, render(report))
    finished = perf_counter()
    print_report(
        report,
        f"Wrote {out}. Load data and models {loaded - started:.1f} s; retrieval "
        f"{retrieved - loaded:.1f} s; scorers {finished - retrieved:.1f} s; total "
        f"{finished - started:.1f} s on {platform.machine()} {platform.system()}, "
        f"Python {platform.python_version()}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
