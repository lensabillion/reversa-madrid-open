"""The Jev judge's core: PR #63's frozen prompt, and a cached, budgeted runner for it.

Taken from `feat/jev-judge` (part 4's judge for the atlas) without its link rules, which
depend on that branch's masking; lineage uses this core for its reworded origins.

Owner decision D1, 3 October 2026: Jev (TypeSafe `jev-1.13.0`) judges every candidate on
the live path. The state and the four questions are PR #63's `legal-change-v1` prompt,
verbatim, because the publication cutoff was measured on Jev's answers to exactly these
questions: on LobbyPlag's 272 practice pairs, requiring all four answers to clear 0.67
selected 58 pairs, 57 of them verified copies (precision 0.983, Wilson 95% lower bound
0.909). Changing a word of a question or of the state invalidates that measurement.

A pair is published only when the rules allow it too: the ask came first, the rules found
no opposite legal force, and the matched wording is mostly the submitter's own rather than
text quoted from the Commission's proposal. Jev's answers are evidence that a request and
an amendment make the same legal change; they are not proof that one caused the other.
"""

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError

from influence.extraction.files import write_bytes_atomic
from influence.schemas.atlas import Amendment, Ask
from influence.services.jev import (
    MAX_REQUEST_BYTES,
    REQUEST_TOKEN_RESERVE,
    JevClient,
    JevError,
    JevRequest,
    JevResult,
    NoulAnswer,
    NoulQuestion,
)

CUTOFF = 0.67
# TypeSafe's input price as PR #63 recorded it; the cap is accounting, not a billing promise.
PRICE_PER_TOKEN = 0.042 / 1_000_000
RESERVE_USD = REQUEST_TOKEN_RESERVE * PRICE_PER_TOKEN
_BEFORE, _AFTER = 1200, 300
_ARTICLE = re.compile(r"Article\s+(\d+)", re.IGNORECASE)
_QUESTIONS = {
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


class _LegalState(BaseModel):
    """PR #63's `LegalState`, field for field and in order: the order fixes the request bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    submission_old: str | None
    submission_new: str
    preceding_context: str
    following_context: str
    amendment_old: str | None
    amendment_new: str
    proposal_text: str | None
    proposal_context_status: str


@dataclass(frozen=True)
class JevAnswers:
    actual_request: float
    same_legal_change: float
    incompatible_legal_change: float
    shared_background: float

    @property
    def support(self) -> float:
        """The weakest of the four answers, each read in the direction that supports a link."""
        return min(
            self.actual_request,
            self.same_legal_change,
            1 - self.shared_background,
            1 - self.incompatible_legal_change,
        )


def request_bytes(request: JevRequest) -> bytes:
    """The adapter's exact wire encoding, so a cache key names the bytes that were sent."""
    return json.dumps(
        request.model_dump(exclude_none=True), ensure_ascii=False, allow_nan=False
    ).encode()


def _request(state: _LegalState) -> JevRequest:
    payload: dict[str, JsonValue] = state.model_dump(mode="json")
    return JevRequest(
        state=payload,
        questions={key: NoulQuestion(instructions=text) for key, text in _QUESTIONS.items()},
    )


def proposal_articles(articles: Iterable[tuple[str, str]]) -> dict[str, str]:
    """`(provision, text)` of the proposal's articles, first wins, keyed as `article 5`."""
    found: dict[str, str] = {}
    for provision, text in articles:
        found.setdefault(provision.casefold(), text)
    return found


def judge_request(
    ask: Ask, amendment: Amendment, source_text: str, proposal: Mapping[str, str]
) -> JevRequest | None:
    """The question for one pair, or None when it cannot fit the provider's byte bound.

    PR #63's `proposal-v1` context: 1,200 characters before the ask and 300 after, and the
    proposal article the amendment targets when one matches exactly. That article is the
    only thing dropped to fit the bound; the ask and the amendment are never truncated.
    """
    target = _ARTICLE.search(amendment.target_provision or "")
    article = proposal.get(f"article {target[1]}") if target is not None else None
    state = _LegalState(
        submission_old=None,
        submission_new=ask.span.text,
        preceding_context=source_text[max(0, ask.span.start - _BEFORE) : ask.span.start],
        following_context=source_text[ask.span.end : ask.span.end + _AFTER],
        amendment_old=amendment.old_text,
        amendment_new=amendment.new_text,
        proposal_text=article,
        proposal_context_status="unavailable_no_exact_provision"
        if article is None
        else "exact_target_provision",
    )
    request = _request(state)
    if article is not None and len(request_bytes(request)) > MAX_REQUEST_BYTES:
        request = _request(
            state.model_copy(
                update={
                    "proposal_text": None,
                    "proposal_context_status": "omitted_full_provision_exceeds_request_bound",
                }
            )
        )
    return request if len(request_bytes(request)) <= MAX_REQUEST_BYTES else None


def _answers(result: JevResult) -> JevAnswers:
    values: dict[str, float] = {}
    for key in _QUESTIONS:
        answer = result.answers.get(key)
        if not isinstance(answer, NoulAnswer):
            raise JevError(f"Jev returned no Noul value for {key}")
        values[key] = answer.noul
    return JevAnswers(**values)


@dataclass(frozen=True)
class JudgeReport:
    """What one run asked: answers by request key, failures by reason, and the spend."""

    answers: dict[str, JevAnswers]
    failures: dict[str, str]
    cached: int
    asked: int
    spent_usd: float


@dataclass(frozen=True)
class JevJudge:
    """Asks Jev once per distinct request, caches every answer, and stops at a dollar cap.

    The cache is content-addressed (`<sha256 of the request bytes>.json`), so a rerun of
    the same law costs nothing and a changed prompt or input can never reuse a stale answer.
    Calls run `workers` at a time. Before each batch the worst case (the provider's full
    context per call) must fit under `max_usd`; spend is then counted from returned usage.
    """

    client: JevClient
    cache: Path
    max_usd: float
    workers: int = 16

    def _cached(self, key: str) -> JevResult | None:
        path = self.cache / f"{key}.json"
        if not path.is_file():
            return None
        try:
            return JevResult.model_validate_json(path.read_bytes())
        except ValidationError:
            return None

    def _ask(self, key: str, request: JevRequest) -> JevResult:
        result = self.client.evaluate(request.state, request.questions)
        write_bytes_atomic(self.cache / f"{key}.json", result.model_dump_json().encode())
        return result

    def run(self, requests: Iterable[JevRequest]) -> JudgeReport:
        unique = {hashlib.sha256(request_bytes(r)).hexdigest(): r for r in requests}
        results: dict[str, JevResult] = {}
        failures: dict[str, str] = {}
        pending: list[str] = []
        for key in unique:
            if (cached := self._cached(key)) is not None:
                results[key] = cached
            else:
                pending.append(key)
        cached_count, spent = len(results), 0.0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for first in range(0, len(pending), self.workers):
                batch = pending[first : first + self.workers]
                if spent + len(batch) * RESERVE_USD > self.max_usd:
                    failures.update(
                        (key, f"not asked: the ${self.max_usd:.2f} Jev budget was reached")
                        for key in pending[first:]
                    )
                    break
                futures = {key: pool.submit(self._ask, key, unique[key]) for key in batch}
                for key, future in futures.items():
                    try:
                        result = future.result()
                    except (JevError, OSError) as error:
                        failures[key] = f"Jev call failed: {error}"
                        spent += RESERVE_USD  # A failed call may still be billed.
                        continue
                    results[key] = result
                    spent += result.usage.input_tokens * PRICE_PER_TOKEN
        answers: dict[str, JevAnswers] = {}
        for key, result in results.items():
            try:
                answers[key] = _answers(result)
            except JevError as error:
                failures[key] = str(error)
        return JudgeReport(
            answers=answers,
            failures=failures,
            cached=cached_count,
            asked=len(results) - cached_count,
            spent_usd=spent,
        )
