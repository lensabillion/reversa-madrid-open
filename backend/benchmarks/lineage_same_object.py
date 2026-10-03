"""Measure the second Jev stage (`same_object`) on LobbyPlag's labelled pairs before using it.

The reworded-origin rule asks Jev four frozen questions (`jev_judge`, PR #63) and keeps a
pair whose weakest supporting answer clears `CUTOFF`. On the AI Act that rule kept a pair
with the same safeguard on a different object. The second stage asks one more question,
`jev_judge.SAME_OBJECT_QUESTION`, of the same state. This script asks it of every practice
pair (the 272 of `benchmarks/lineage_practice.py`, built the same way, so the four answers
come from that script's cache) and reports precision and recall with and without it, at the
practice threshold (0.5, each answer read in its supporting direction) and at the pipeline's
`CUTOFF`. Answers are cached by request hash under `--cache`; a rerun costs nothing.

From backend (after `benchmarks/lineage_practice.py --execute` filled `--four`):
    uv run --locked python -m benchmarks.lineage_same_object --data ../data/lobbyplag \\
        --four ../data/lineage-practice --cache ../data/lineage-same-object \\
        --out evaluation/lineage-same-object.json [--execute --max-cost-usd 0.2]
"""

import argparse
import hashlib
import json
import ssl
from collections.abc import Sequence
from pathlib import Path

from pydantic import JsonValue

from benchmarks.lineage_jev import LegalState, body_of, credential, request_for
from benchmarks.lineage_practice import counts
from influence.extraction.files import write_bytes_atomic
from influence.practice.labels import LabelledPair, build_practice_set
from influence.repositories.lobbyplag import DemoRepository
from influence.services.jev import JevClient, JevRequest, JevResult
from influence.services.jev_judge import (
    CUTOFF,
    SAME_OBJECT,
    SAME_OBJECT_REVISION,
    JevJudge,
    same_object_request,
)

PRACTICE_THRESHOLD = 0.5


def support(answers: dict[str, float]) -> float:
    """The weakest of the four answers read in the direction that supports a link."""
    return min(
        answers["actual_request"],
        answers["same_legal_change"],
        1 - answers["incompatible_legal_change"],
        1 - answers["shared_background"],
    )


def rule_counts(keep: Sequence[bool], pairs: Sequence[LabelledPair]) -> dict[str, JsonValue]:
    return counts(list(keep), pairs)


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--data", type=Path, required=True, help="data/lobbyplag")
    parser.add_argument("--four", type=Path, required=True, help="lineage_practice's cache")
    parser.add_argument("--cache", type=Path, required=True, help="same-object answer cache")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--execute", action="store_true", help="call Jev (costs money)")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--max-cost-usd", type=float, default=0.2)
    args = parser.parse_args()

    pairs = build_practice_set(DemoRepository.load(args.data)).pairs
    four: list[dict[str, float]] = []
    second: list[JevRequest] = []
    for item in pairs:
        submission = item.pair.submission
        request = request_for(
            LegalState(
                submission_old=submission.old if submission.old.strip() else None,
                submission_new=submission.new,
                preceding_context="",
                following_context="",
                amendment_old=item.pair.amendment.old,
                amendment_new=item.pair.amendment.new,
                proposal_text=None,
                proposal_context_status="not_supplied",
            )
        )
        path = args.four / f"{hashlib.sha256(body_of(request)).hexdigest()}.json"
        if not path.is_file():
            raise SystemExit(f"Four-question answer missing: run lineage_practice first ({path})")
        result = JevResult.model_validate_json(path.read_bytes())
        four.append({k: a.noul for k, a in result.answers.items() if a.type == "noul"})
        second.append(same_object_request(request))

    args.cache.mkdir(parents=True, exist_ok=True)
    keys = [hashlib.sha256(body_of(r)).hexdigest() for r in second]
    if args.execute:
        judge = JevJudge(
            client=JevClient(credential(args.env_file), ssl.create_default_context()),
            cache=args.cache,
            max_usd=args.max_cost_usd,
        )
        report = judge.same_object(second)
        print(f"asked {report.asked}, cached {report.cached}, spent {report.spent_usd:.4f} USD")
        if report.failures:
            raise SystemExit(f"{len(report.failures)} same-object answers failed")
    same: list[float] = []
    for key in keys:
        path = args.cache / f"{key}.json"
        if not path.is_file():
            raise SystemExit("Same-object answers missing: run with --execute")
        answer = JevResult.model_validate_json(path.read_bytes()).answers[SAME_OBJECT]
        if answer.type != "noul":
            raise SystemExit("Same-object answer is not a probability")
        same.append(answer.noul)

    out: dict[str, JsonValue] = {
        "pairs": len(pairs),
        "positives": sum(p.influenced for p in pairs),
        "second_stage": SAME_OBJECT_REVISION,
    }
    for name, threshold in (("practice_0.5", PRACTICE_THRESHOLD), ("pipeline_cutoff", CUTOFF)):
        four_rule = [support(a) >= threshold for a in four]
        both = [f and s >= threshold for f, s in zip(four_rule, same, strict=True)]
        out[name] = {
            "threshold": threshold,
            "four_questions": rule_counts(four_rule, pairs),
            "four_and_same_object": rule_counts(both, pairs),
            "dropped_true": sum(
                f and not b and p.influenced for f, b, p in zip(four_rule, both, pairs, strict=True)
            ),
            "dropped_false": sum(
                f and not b and not p.influenced
                for f, b, p in zip(four_rule, both, pairs, strict=True)
            ),
        }
    text = json.dumps(out, indent=2)
    print(text)
    if args.out is not None:
        write_bytes_atomic(args.out, (text + "\n").encode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
