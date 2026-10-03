"""Lineage, reworded origins: ask Jev whether a consultation passage asks for an adopted amendment.

Verbatim lineage (`services/lineage.py`, `services/origin.py`) finds the amendments whose
inserted wording reached the final act, and the submissions that repeat that wording word for
word. On the AI Act that second step finds almost nothing (4 matches in 788 submissions),
because organisations ask in their own words. This script covers the reworded case:

1. The amendments that adopted wording into the final act (`lineage.adopt`), 363 on the AI Act.
2. For each, the passages whose rare words its change shares (BM25, the same
   `pipeline.find_candidates` part 3 uses): `CANDIDATES_PER_AMENDMENT` per amendment.
3. Each (passage, amendment) pair goes to TypeSafe's Jev with the four questions and the
   state shape of the Gate 3 trial (`feat/jev-gate-three`), unchanged, so the answers mean
   what that evaluation measured. Jev only scores; nothing here quotes or publishes.

Without `--execute` it is a dry run: it reads no credential, calls nothing, and prints the
number of requests, their bytes and a cost estimate. With `--execute` it reads
`TYPESAFE_API_KEY` from `--env-file` (or from the environment when no file is given), and
stops before the cumulative charge could pass `--max-cost-usd`, reserving the provider's
whole 65,536-token allowance per call as the Gate 3 runner does. Answers are cached by the
hash of the request under `data/laws/<slug>/lineage-jev/`, so a rerun costs nothing.

Output: `data/laws/<slug>/lineage-jev.json`, one row per pair with the four probabilities.
`benchmarks/lineage_view.py` turns those rows and the verbatim origins into the explorer's
`atlas.json`.

From backend: uv run --locked python benchmarks/lineage_jev.py --law ../data/laws/2021-0106-COD
"""

import argparse
import hashlib
import json
import os
import shlex
import ssl
import sys
from pathlib import Path
from time import perf_counter
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr

from influence.extraction.files import write_bytes_atomic
from influence.services.jev import (
    MAX_REQUEST_BYTES,
    REQUEST_TOKEN_RESERVE,
    JevClient,
    JevError,
    JevRequest,
    JevResult,
    NoulQuestion,
)
from influence.services.lineage import adopt
from influence.services.pipeline import asks_from_passages, find_candidates, load_collected

PRICE_PER_TOKEN = 0.042 / 1_000_000
RESERVE_USD = REQUEST_TOKEN_RESERVE * PRICE_PER_TOKEN
# Context around the passage, as in the Gate 3 trial's first context version.
BEFORE_CHARS = 1200
AFTER_CHARS = 300
# The Gate 3 questions, word for word: changing them would change what the answers mean.
QUESTIONS = {
    "actual_request": (
        "Does the submission express an identifiable requested legal change? When "
        "submission_old is supplied, interpret submission_old to submission_new as the "
        "source's explicitly specified legislative edit (including pure deletion). When "
        "submission_old is null, classify the cited submission_new using context: a "
        "glossary, historical description or existing law alone is not a request."
    ),
    "same_legal_change": (
        "Does the identifiable submission request ask for the actual change from "
        "amendment_old to amendment_new, with the same regulated actor, action, scope, "
        "conditions and legal force? For known submission_old compare the two edits. "
        "Shared topic or unchanged wording is insufficient. Null original text is unknown; "
        "never infer an insertion or deletion from it."
    ),
    "incompatible_legal_change": (
        "Do the requested legal effect and the amendment's actual change impose "
        "incompatible requirements on the same actor, action, scope and conditions? "
        "Negation elsewhere is insufficient. Permission does not establish duty. "
        "Absence of entailment alone is not contradiction. Unknown originals remain unknown."
    ),
    "shared_background": (
        "Does the supplied text or context explicitly identify matching wording as "
        "existing law, background, or an earlier third-party definition, rather than "
        "this submitter's own requested change? A known old/new submission edit keeps "
        "unchanged old wording as background. Lack of explicit attribution does not "
        "prove originality; answer only from the provided evidence."
    ),
}


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class LegalState(Contract):
    """The Gate 3 state; the proposal context is not supplied in this first version."""

    submission_old: str | None
    submission_new: str
    preceding_context: str
    following_context: str
    amendment_old: str | None
    amendment_new: str
    proposal_text: str | None
    proposal_context_status: str


class Pair(Contract):
    ask_id: str
    passage_id: str
    amendment_id: str
    lexical_rank: int | None
    request_sha256: str
    request_bytes: int


class Row(Contract):
    ask_id: str
    passage_id: str
    amendment_id: str
    lexical_rank: int | None
    answers: dict[str, float] = Field(default_factory=dict)
    skipped: str | None = None


def request_for(state: LegalState) -> JevRequest:
    return JevRequest(
        state=cast(dict[str, JsonValue], state.model_dump(mode="json")),
        questions={key: NoulQuestion(instructions=text) for key, text in QUESTIONS.items()},
    )


def body_of(request: JevRequest) -> bytes:
    return json.dumps(
        request.model_dump(exclude_none=True), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def credential(env_file: Path | None) -> SecretStr:
    """The key from the explicit file, else from the environment; never printed."""
    if env_file is None:
        value = os.environ.get("TYPESAFE_API_KEY", "").strip()
        if not value:
            raise SystemExit("Set TYPESAFE_API_KEY or pass --env-file")
        return SecretStr(value)
    values: list[str] = []
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.removeprefix("export ").partition("=")
        if separator and key.strip() == "TYPESAFE_API_KEY":
            parts = shlex.split(value.strip(), comments=True)
            if len(parts) != 1:
                raise SystemExit("Malformed TYPESAFE_API_KEY entry")
            values.append(parts[0])
    if len(values) != 1 or not values[0].strip():
        raise SystemExit("Expected one nonempty TYPESAFE_API_KEY in the env file")
    return SecretStr(values[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--law", type=Path, required=True, help="data/laws/<slug> bundle")
    parser.add_argument("--execute", action="store_true", help="call Jev (costs money)")
    parser.add_argument("--env-file", type=Path, help="file holding TYPESAFE_API_KEY")
    parser.add_argument("--max-cost-usd", type=float, default=1.0)
    parser.add_argument("--limit", type=int, help="only the first N pairs (a trial)")
    args = parser.parse_args()

    started = perf_counter()
    collected = load_collected(args.law)
    adoption = adopt(collected)
    adopting = {a.amendment_id for a in adoption.adoptions}
    amendments = {a.amendment_id: a for a in collected.amendments}
    asks = asks_from_passages(collected.passages)
    asks_by_id = {ask.ask_id: ask for ask in asks}
    texts = {t.document_id: t.text for t in collected.document_texts}
    candidates = find_candidates((amendments[i] for i in sorted(adopting)), asks)
    if args.limit is not None:
        candidates = candidates[: args.limit]

    pairs: list[Pair] = []
    requests: dict[str, bytes] = {}
    skipped: list[Row] = []
    for candidate in candidates:
        ask = asks_by_id[candidate.ask_id]
        amendment = amendments[candidate.amendment_id]
        text = texts[ask.document_id]
        state = LegalState(
            submission_old=None,
            submission_new=ask.span.text,
            preceding_context=text[max(0, ask.span.start - BEFORE_CHARS) : ask.span.start],
            following_context=text[ask.span.end : ask.span.end + AFTER_CHARS],
            amendment_old=amendment.old_text,
            amendment_new=amendment.new_text,
            proposal_text=None,
            proposal_context_status="not_supplied",
        )
        body = body_of(request_for(state))
        if len(body) > MAX_REQUEST_BYTES:
            skipped.append(
                Row(
                    ask_id=ask.ask_id,
                    passage_id=ask.passage_id or ask.ask_id,
                    amendment_id=amendment.amendment_id,
                    lexical_rank=candidate.lexical_rank,
                    skipped=f"request of {len(body)} bytes exceeds {MAX_REQUEST_BYTES}",
                )
            )
            continue
        digest = hashlib.sha256(body).hexdigest()
        requests[digest] = body
        pairs.append(
            Pair(
                ask_id=ask.ask_id,
                passage_id=ask.passage_id or ask.ask_id,
                amendment_id=amendment.amendment_id,
                lexical_rank=candidate.lexical_rank,
                request_sha256=digest,
                request_bytes=len(body),
            )
        )

    cache = args.law / "lineage-jev"
    cache.mkdir(exist_ok=True)
    cached = {d for d in requests if (cache / f"{d}.json").is_file()}
    to_send = [d for d in requests if d not in cached]
    total_bytes = sum(len(requests[d]) for d in to_send)
    print(
        f"{len(adopting)} adopting amendments, {len(candidates)} candidate pairs, "
        f"{len(skipped)} over the byte bound, {len(requests)} distinct requests "
        f"({len(cached)} cached, {len(to_send)} to send, {total_bytes:,} bytes)"
    )
    print(
        f"estimate: about {total_bytes / 4 * PRICE_PER_TOKEN:.2f} USD at 4 bytes a token; "
        f"worst case reserved {len(to_send) * RESERVE_USD:.2f} USD"
    )

    if args.execute and to_send:
        client = JevClient(credential(args.env_file), ssl.create_default_context())
        ledger_path = cache / "ledger.json"
        spent = (
            float(json.loads(ledger_path.read_text())["spent_usd"])
            if ledger_path.is_file()
            else 0.0
        )
        for number, digest in enumerate(to_send, 1):
            if spent + RESERVE_USD > args.max_cost_usd:
                print(f"stopped: {spent:.4f} USD spent, the next call could pass the cap")
                break
            request = JevRequest.model_validate_json(requests[digest])
            # A failed call may still be billed: charge the reservation until usage returns.
            spent += RESERVE_USD
            write_bytes_atomic(ledger_path, json.dumps({"spent_usd": spent}).encode())
            try:
                result = client.evaluate(request.state, request.questions)
            except JevError as error:
                print(f"request {digest[:12]} failed: {error}", file=sys.stderr)
                continue
            spent += result.usage.input_tokens * PRICE_PER_TOKEN - RESERVE_USD
            write_bytes_atomic(ledger_path, json.dumps({"spent_usd": spent}).encode())
            write_bytes_atomic(cache / f"{digest}.json", result.model_dump_json().encode())
            if number % 50 == 0:
                print(f"{number}/{len(to_send)} sent, {spent:.4f} USD", flush=True)
        print(f"spent so far: {spent:.4f} USD")

    rows = list(skipped)
    for pair in pairs:
        path = cache / f"{pair.request_sha256}.json"
        answers: dict[str, float] = {}
        if path.is_file():
            result = JevResult.model_validate_json(path.read_bytes())
            answers = {
                key: answer.noul for key, answer in result.answers.items() if answer.type == "noul"
            }
        rows.append(
            Row(
                ask_id=pair.ask_id,
                passage_id=pair.passage_id,
                amendment_id=pair.amendment_id,
                lexical_rank=pair.lexical_rank,
                answers=answers,
                skipped=None if answers else "not judged yet",
            )
        )
    out = args.law / "lineage-jev.json"
    write_bytes_atomic(
        out, json.dumps([row.model_dump(mode="json") for row in rows], indent=1).encode()
    )
    judged = [row for row in rows if row.answers]
    strong = [
        row
        for row in judged
        if row.answers.get("same_legal_change", 0) >= 0.5
        and row.answers.get("actual_request", 0) >= 0.5
    ]
    print(
        f"{len(judged)} pairs judged, {len(strong)} with same_legal_change and "
        f"actual_request >= 0.5; wrote {out} in {perf_counter() - started:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
