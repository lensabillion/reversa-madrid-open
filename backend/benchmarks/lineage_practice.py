"""Measure the lineage pipeline's two link rules on LobbyPlag's labelled pairs.

The lineage explorer (`benchmarks/lineage_view.py`) links a submission to an amendment by
one of two rules. This scores both on the practice set the other scorers use (272 pairs,
172 volunteer-verified, 100 crowd-rejected; organisation-grouped folds; the same simulated
tests of 30 + 30 with seed 0), so the numbers compare with `evaluation/practice-results.json`:

* verbatim: the amendment's inserted words and the submission's wording share a run of at
  least `MIN_ADOPTED_RUN_WORDS` (12) words, the rule `services/origin.py` applies. The score
  is the longest shared run over 24, capped at 1, so the harness's 0.5 recall threshold is
  exactly the 12-word rule;
* reworded: Jev's four Gate 3 answers, with the request and state of
  `benchmarks/lineage_jev.py` (submission old/new known here). The link rule is
  `same_legal_change` and `actual_request` >= 0.5 with neither `incompatible_legal_change`
  nor `shared_background` >= 0.5. Without `--execute` it is a dry run that only counts the
  requests; answers are cached by request hash under `--cache`.

It also re-measures BM25 recall@5 (the shortlist Jev sees) with part 3's index, because a
pair BM25 does not shortlist never reaches Jev: the pipeline's recall is at most that.

From backend:
    uv run --locked python benchmarks/lineage_practice.py --data ../data/lobbyplag \
        --cache ../data/lineage-practice [--execute --env-file .env --max-cost-usd 1]
"""

import argparse
import hashlib
import json
import ssl
from collections.abc import Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from benchmarks.lineage_jev import (
    PRICE_PER_TOKEN,
    RESERVE_USD,
    LegalState,
    body_of,
    credential,
    request_for,
)
from influence.extraction.files import write_bytes_atomic
from influence.practice.calibrate import wilson_interval
from influence.practice.folds import make_folds
from influence.practice.harness import SimulationSettings, evaluate, simulated_tests
from influence.practice.labels import LabelledPair, build_practice_set
from influence.practice.recall import build_index
from influence.repositories.lobbyplag import DemoRepository
from influence.schemas.lineage import MIN_ADOPTED_RUN_WORDS
from influence.services.jev import JevClient, JevError, JevRequest, JevResult
from influence.services.prose_match import words_of

FOLDS = 5
DRAWS = 2000
PER_CLASS = 30
SEED = 0
TOP_K = 20
THRESHOLD = 0.5


def longest_inserted_run(old: str, new: str, submission: str) -> int:
    """Longest run of the amendment's inserted words that the submission repeats.

    Word diff of old against new (O(n m)), then the longest common block of each inserted
    block against the submission (O(b s)); designed for amendments of a few hundred words.
    """
    old_words = [w.text for w in words_of(old)]
    new_words = [w.text for w in words_of(new)]
    target = [w.text for w in words_of(submission)]
    blocks = [
        new_words[j1:j2]
        for tag, _, _, j1, j2 in SequenceMatcher(
            None, old_words, new_words, autojunk=False
        ).get_opcodes()
        if tag in ("insert", "replace")
    ]
    best = 0
    for block in blocks:
        match = SequenceMatcher(None, block, target, autojunk=False).find_longest_match(
            0, len(block), 0, len(target)
        )
        best = max(best, match.size)
    return best


def counts(decisions: Sequence[bool], pairs: Sequence[LabelledPair]) -> dict[str, JsonValue]:
    tp = sum(d and p.influenced for d, p in zip(decisions, pairs, strict=True))
    fp = sum(d and not p.influenced for d, p in zip(decisions, pairs, strict=True))
    positives = sum(p.influenced for p in pairs)
    low, high = wilson_interval(tp, tp + fp) if tp + fp else (0.0, 0.0)
    return {
        "selected": tp + fp,
        "true_positives": tp,
        "false_positives": fp,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "precision_wilson95": [round(low, 4), round(high, 4)],
        "recall": round(tp / positives, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--data", type=Path, required=True, help="data/lobbyplag")
    parser.add_argument("--cache", type=Path, required=True, help="Jev answer cache directory")
    parser.add_argument("--out", type=Path, help="write the report here as JSON")
    parser.add_argument("--execute", action="store_true", help="call Jev (costs money)")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-cost-usd", type=float, default=1.0)
    args = parser.parse_args()

    repository = DemoRepository.load(args.data)
    practice = build_practice_set(repository)
    pairs = practice.pairs
    plan = make_folds(pairs, FOLDS)
    tests = simulated_tests([p.influenced for p in pairs], DRAWS, PER_CLASS, SEED)
    settings = SimulationSettings(
        draws=DRAWS,
        per_class=PER_CLASS,
        seed=SEED,
        generator="Python random.Random (Mersenne Twister)",
        top_k=TOP_K,
        recall_threshold=THRESHOLD,
    )
    report: dict[str, JsonValue] = {
        "pairs": len(pairs),
        "positives": sum(p.influenced for p in pairs),
        "folds": FOLDS,
        "draws": DRAWS,
        "seed": SEED,
    }

    runs = [
        longest_inserted_run(p.pair.amendment.old, p.pair.amendment.new, p.pair.submission.new)
        for p in pairs
    ]
    verbatim = [min(1.0, run / (2 * MIN_ADOPTED_RUN_WORDS)) for run in runs]
    result = evaluate("verbatim 12-word run", verbatim, pairs, plan, tests, settings)
    report["verbatim"] = {
        "full_set_auc": result.full_set_auc,
        "precision_at_20_mean": round(result.draws.precision_at_top.mean, 4),
        "rule_12_words": counts([run >= MIN_ADOPTED_RUN_WORDS for run in runs], pairs),
    }

    # BM25 shortlist recall: one search per distinct verified amendment, k = 5 as in the
    # pipeline (`CANDIDATES_PER_AMENDMENT`), corpus of the proposals' new wording.
    index = build_index(repository, "new_text_only")
    verified = [p for p in pairs if p.influenced]
    hits = 0
    for item in verified:
        try:
            shortlist = index.search(
                item.pair.amendment_id, item.pair.amendment.old, item.pair.amendment.new, k=5
            )
        except ValueError:
            continue
        hits += any(c.passage.document_id == item.pair.proposal_id for c in shortlist.candidates)
    report["bm25_recall_at_5"] = round(hits / len(verified), 4)

    bodies: list[bytes] = []
    for item in pairs:
        submission = item.pair.submission
        state = LegalState(
            submission_old=submission.old if submission.old.strip() else None,
            submission_new=submission.new,
            preceding_context="",
            following_context="",
            amendment_old=item.pair.amendment.old,
            amendment_new=item.pair.amendment.new,
            proposal_text=None,
            proposal_context_status="not_supplied",
        )
        bodies.append(body_of(request_for(state)))
    args.cache.mkdir(parents=True, exist_ok=True)
    digests = [hashlib.sha256(body).hexdigest() for body in bodies]
    missing = sorted({d for d in digests if not (args.cache / f"{d}.json").is_file()})
    size = sum(len(bodies[digests.index(d)]) for d in missing)
    print(
        f"Jev: {len(set(digests))} distinct requests, {len(missing)} not cached "
        f"({size:,} bytes, about {size / 4 * PRICE_PER_TOKEN:.3f} USD)"
    )
    if args.execute and missing:
        client = JevClient(credential(args.env_file), ssl.create_default_context())
        spent = 0.0
        for digest in missing:
            if spent + RESERVE_USD > args.max_cost_usd:
                print(f"stopped at {spent:.4f} USD: the next call could pass the cap")
                break
            request = JevRequest.model_validate_json(bodies[digests.index(digest)])
            spent += RESERVE_USD
            try:
                answer = client.evaluate(request.state, request.questions)
            except JevError as error:
                print(f"request {digest[:12]} failed: {error}")
                continue
            spent += answer.usage.input_tokens * PRICE_PER_TOKEN - RESERVE_USD
            write_bytes_atomic(args.cache / f"{digest}.json", answer.model_dump_json().encode())
        print(f"spent {spent:.4f} USD (failed calls count at their full reservation)")

    answers: list[dict[str, float] | None] = []
    for digest in digests:
        path = args.cache / f"{digest}.json"
        if path.is_file():
            parsed = JevResult.model_validate_json(path.read_bytes())
            answers.append({k: a.noul for k, a in parsed.answers.items() if a.type == "noul"})
        else:
            answers.append(None)
    judged = [a for a in answers if a is not None]
    if len(judged) == len(pairs):
        complete = cast(list[dict[str, float]], answers)
        same = [a["same_legal_change"] for a in complete]
        rule = [
            a["same_legal_change"] >= THRESHOLD
            and a["actual_request"] >= THRESHOLD
            and a["incompatible_legal_change"] < THRESHOLD
            and a["shared_background"] < THRESHOLD
            for a in complete
        ]
        jev = evaluate("jev same_legal_change", same, pairs, plan, tests, settings)
        either = [
            v or r
            for v, r in zip([run >= MIN_ADOPTED_RUN_WORDS for run in runs], rule, strict=True)
        ]
        report["jev"] = {
            "full_set_auc_same_legal_change": jev.full_set_auc,
            "precision_at_20_mean": round(jev.draws.precision_at_top.mean, 4),
            "link_rule": counts(rule, pairs),
        }
        report["pipeline_verbatim_or_jev"] = counts(either, pairs)
    else:
        report["jev"] = f"{len(judged)} of {len(pairs)} pairs judged; run with --execute"

    text = json.dumps(report, indent=2)
    print(text)
    if args.out is not None:
        write_bytes_atomic(args.out, (text + "\n").encode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
