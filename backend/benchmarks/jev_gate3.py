"""Bounded Part 4 diagnostic trial: prepare, dry-run/run, report; never publish links.

From backend: uv run --locked python benchmarks/jev_gate3.py --help.
Only `run --execute --env-file PATH` reads a credential or calls the provider. The one
operator must reuse the same output directory: its ledger retains failed reservations.
"""

import argparse
import hashlib
import json
import re
import shlex
import ssl
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr

from influence.extraction.files import write_bytes_atomic
from influence.schemas.atlas import Amendment, ArticleVersion, Ask, LinkAssessment
from influence.schemas.atlas_view import AtlasView
from influence.services.jev import (
    MAX_REQUEST_BYTES,
    MODEL,
    REQUEST_TOKEN_RESERVE,
    ChoiceAnswer,
    ChoiceQuestion,
    JevClient,
    JevRequest,
    JevResult,
    NoulQuestion,
)
from influence.services.pipeline import load_collected

ATLAS_SHA256 = "ec377825c4c2110cfdb2a76efd82188bc80987419a7d927f17877542ac909fde"
PRICE_PER_TOKEN = 0.042 / 1_000_000
RESERVE_USD = REQUEST_TOKEN_RESERVE * PRICE_PER_TOKEN
REAL_PAIRS = (
    ("090166e5d35cddb0-32", "ITRE-PE719.802-270"),
    ("090166e5e09de27a-104", "ITRE-PE719.802-270"),
    ("090166e5e01fd5e7-64", "IMCO-LIBE-PE732.840-2148"),
    ("090166e5e09a6421-38", "IMCO-LIBE-PE732.841-2699"),
    ("090166e5e08e7cd5-35", "IMCO-LIBE-PE732.838-1538"),
    ("090166e5d36af711-6", "CULT-PE730.175-195"),
    ("090166e5d35f183c-158", "IMCO-LIBE-PE732.840-2088"),
    ("090166e5df9dc440-15", "IMCO-LIBE-PE732.844-3155"),
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class NliState(Contract):
    premise: str
    hypothesis: str


class LegalState(Contract):
    submission_old: str | None
    submission_new: str
    preceding_context: str
    following_context: str
    amendment_old: str | None
    amendment_new: str
    proposal_text: str | None
    proposal_context_status: str


class PreparedCase(Contract):
    case_id: str
    family: Literal["nli-v1", "legal-change-v1"]
    state: dict[str, JsonValue]
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class PreparedTrial(Contract):
    schema_version: Literal["jev-gate3-inputs-1"] = "jev-gate3-inputs-1"
    source_hashes: dict[str, str]
    cases: list[PreparedCase]


class Entry(Contract):
    case_id: str
    status: Literal["pending", "complete", "failed"]
    reserved_usd: float = Field(ge=0)
    actual_cost_usd: float | None = Field(default=None, ge=0)
    result_sha256: str | None = None
    error_type: str | None = None
    elapsed_seconds: float | None = None


class Ledger(Contract):
    schema_version: Literal["jev-usage-ledger-1"] = "jev-usage-ledger-1"
    entries: dict[str, Entry] = Field(default_factory=dict)


class CachedResult(Contract):
    request_sha256: str
    completed_at: str
    elapsed_seconds: float = Field(ge=0)
    response: JevResult


def write(path: Path, value: BaseModel | dict[str, object]) -> None:
    """Use the repository's atomic writer; artifacts never contain API credentials."""
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    write_bytes_atomic(
        path, json.dumps(raw, ensure_ascii=False, allow_nan=False, indent=2).encode()
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_request(case: PreparedCase) -> JevRequest:
    """One frozen question family per state kind; caller metadata is never submitted."""
    if case.family == "nli-v1":
        state = NliState.model_validate(case.state)
        return JevRequest(
            state=cast(dict[str, JsonValue], state.model_dump(mode="json")),
            questions={
                "relation": ChoiceQuestion(
                    instructions=(
                        "Classify the directional relationship from premise to hypothesis. "
                        "Use only the supplied statements. Permission does not entail duty. "
                        "Missing information is neutral, not contradiction."
                    ),
                    criteria={
                        "entailment": "The premise makes the hypothesis necessarily true.",
                        "contradiction": (
                            "The premise and hypothesis are incompatible in the same scope."
                        ),
                        "neutral": (
                            "The premise establishes neither the hypothesis nor its negation."
                        ),
                    },
                )
            },
        )
    state = LegalState.model_validate(case.state)
    instructions = {
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
    return JevRequest(
        state=cast(dict[str, JsonValue], state.model_dump(mode="json")),
        questions={key: NoulQuestion(instructions=value) for key, value in instructions.items()},
    )


def request_bytes(request: JevRequest) -> bytes:
    # Match the adapter's wire encoding, including its default JSON whitespace.
    return json.dumps(
        request.model_dump(exclude_none=True), ensure_ascii=False, allow_nan=False
    ).encode()


def key_for(case: PreparedCase) -> str:
    return hashlib.sha256(request_bytes(build_request(case))).hexdigest()


def load_trial(path: Path) -> PreparedTrial:
    trial = PreparedTrial.model_validate_json(path.read_bytes())
    if not trial.cases or len({case.case_id for case in trial.cases}) != len(trial.cases):
        raise ValueError("Cases must be nonempty with unique identifiers")
    for case in trial.cases:
        if len(request_bytes(build_request(case))) > MAX_REQUEST_BYTES:
            raise ValueError(f"Case exceeds provider byte bound; not truncated: {case.case_id}")
    return trial


def real_case(
    link: LinkAssessment,
    ask: Ask,
    amendment: Amendment,
    text: str,
    articles: tuple[ArticleVersion, ...],
    run_id: str,
    *,
    context_version: Literal["proposal-v1", "proposal-v2"] = "proposal-v1",
) -> PreparedCase:
    """Preserve the pilot context policy for every candidate, without scores in model state.

    Article lookup is O(A) per candidate, designed for roughly 1,000 articles/candidates.
    Only a whole supplementary proposal provision may be omitted for the byte bound;
    originals, the exact cited ask and its surrounding context are never truncated.
    """
    before = text[max(0, ask.span.start - 1200) : ask.span.start]
    after = text[ask.span.end : ask.span.end + 300]
    if text[ask.span.start : ask.span.end] != ask.span.text:
        raise ValueError("Ask offsets do not match the frozen original")
    provision = re.search(r"Article\s+(\d+)", amendment.target_provision or "", re.IGNORECASE)
    article = next(
        (
            a
            for a in articles
            if a.stage == "proposal"
            and provision
            and a.provision.casefold() == f"article {provision[1]}"
        ),
        None,
    )
    state = LegalState(
        submission_old=None,
        submission_new=ask.span.text,
        preceding_context=before,
        following_context=after,
        amendment_old=amendment.old_text,
        amendment_new=amendment.new_text,
        proposal_text=None if article is None else article.text,
        proposal_context_status="unavailable_no_exact_provision"
        if article is None
        else "exact_target_provision",
    )
    case = PreparedCase(
        case_id=link.link_id,
        family="legal-change-v1",
        state=cast(dict[str, JsonValue], state.model_dump(mode="json")),
        metadata={
            "ask_id": ask.ask_id,
            "amendment_id": amendment.amendment_id,
            "document_id": ask.document_id,
            "span_start": ask.span.start,
            "span_end": ask.span.end,
            "context_start": max(0, ask.span.start - 1200),
            "proposal_article_id": None if article is None else article.article_id,
            "atlas_run_id": run_id,
        },
    )
    has_proposal = article is not None
    if context_version == "proposal-v2":
        target = re.search(
            r"\b(article|recital)\s+(\d+[a-z]?)\b", amendment.target_provision or "", re.IGNORECASE
        )
        parts: list[ArticleVersion] = []
        if target is not None:
            for candidate in articles:
                label = re.fullmatch(
                    r"(article|recital)\s+(\d+[a-z]?)(?:\s*\([^\n]+\))*",
                    candidate.provision,
                    re.IGNORECASE,
                )
                if (
                    candidate.stage == "proposal"
                    and candidate.procedure_id == amendment.procedure_id
                    and label is not None
                    and tuple(group.casefold() for group in label.group(1, 2))
                    == tuple(group.casefold() for group in target.group(1, 2))
                ):
                    parts.append(candidate)
        has_proposal = bool(parts)
        state = state.model_copy(
            update={
                "proposal_text": "\n\n".join(f"{part.provision}\n{part.text}" for part in parts)
                if parts
                else None,
                "proposal_context_status": "matched_full_provision_records"
                if parts
                else "unavailable_no_matching_proposal_provision",
            }
        )
        case = case.model_copy(
            update={
                "state": state.model_dump(mode="json"),
                "metadata": {
                    **case.metadata,
                    "proposal_context_version": context_version,
                    "target_provision": amendment.target_provision,
                    "proposal_article_id": None,
                    "proposal_article_ids": [part.article_id for part in parts],
                    "proposal_provisions": [part.provision for part in parts],
                    "proposal_document_ids": sorted({part.document_id for part in parts}),
                },
            }
        )
    if len(request_bytes(build_request(case))) > MAX_REQUEST_BYTES and has_proposal:
        state = state.model_copy(
            update={
                "proposal_text": None,
                "proposal_context_status": "omitted_full_provision_exceeds_request_bound",
            }
        )
        case = case.model_copy(update={"state": state.model_dump(mode="json")})
    if (
        ask.ask_id == "ask:passage-doc-hys_attachment-090166e5d35cddb0-32"
        and "AI HLEG" not in before
    ):
        raise ValueError("Required Philips third-party attribution context is missing")
    return case


def prepare(atlas: Path, fixtures: Path, output: Path) -> None:
    """Freeze 24 unchanged diagnostics plus eight explicitly selected, unlabelled real cases."""
    if digest(atlas) != ATLAS_SHA256:
        raise ValueError("Real snapshot differs from the frozen selection")
    view = AtlasView.model_validate_json(atlas.read_bytes())
    source = load_collected(atlas.parent)
    texts = {text.document_id: text.text for text in source.document_texts}
    asks = {ask.ask_id: ask for ask in view.bundle.asks}
    amendments = {am.amendment_id: am for am in view.bundle.amendments}
    cases_file = fixtures / "judge-cases.json"
    fixture = cast(dict[str, JsonValue], json.loads(cases_file.read_bytes()))
    cases = [
        PreparedCase(
            case_id=raw["id"],
            family="nli-v1",
            state={
                "premise": raw["premise"],
                "hypothesis": raw["hypothesis"],
            },
        )
        for raw in cast(list[dict[str, str]], fixture["cases"])
    ]
    if len(cases) != 24:
        raise ValueError("The frozen diagnostic fixture must contain24cases")
    for ask_suffix, amendment_suffix in REAL_PAIRS:
        link_id = (
            f"link:ask-passage-doc-hys_attachment-{ask_suffix}:am-2021-0106-COD-{amendment_suffix}"
        )
        link = next(item for item in view.bundle.links if item.link_id == link_id)
        case = real_case(
            link,
            asks[link.ask_id],
            amendments[link.amendment_id],
            texts[asks[link.ask_id].document_id],
            source.articles,
            view.run_id,
        )
        cases.append(case)
    trial = PreparedTrial(
        source_hashes={
            "atlas": ATLAS_SHA256,
            "judge-cases.json": digest(cases_file),
            "judge-labels.json": digest(fixtures / "judge-labels.json"),
        },
        cases=cases,
    )
    path = output / "inputs.json"
    if path.exists() and PreparedTrial.model_validate_json(path.read_bytes()) != trial:
        raise ValueError("Refusing to overwrite different prepared inputs")
    write(path, trial)
    load_trial(path)
    print(
        json.dumps(
            {
                "prepared": len(cases),
                "families": dict(Counter(c.family for c in cases)),
                "path": str(path),
            }
        )
    )


def prepare_all(
    atlas: Path,
    output: Path,
    *,
    context_version: Literal["proposal-v1", "proposal-v2"] = "proposal-v1",
) -> None:
    """Freeze every non-insufficient real candidate; oversize cases remain explicit exclusions."""
    if digest(atlas) != ATLAS_SHA256:
        raise ValueError("Real snapshot differs from the frozen selection")
    view = AtlasView.model_validate_json(atlas.read_bytes())
    source = load_collected(atlas.parent)
    texts = {text.document_id: text.text for text in source.document_texts}
    asks = {ask.ask_id: ask for ask in view.bundle.asks}
    amendments = {am.amendment_id: am for am in view.bundle.amendments}
    cases: list[PreparedCase] = []
    exclusions: list[dict[str, object]] = []
    selected = sorted(
        (link for link in view.bundle.links if link.status != "insufficient_evidence"),
        key=lambda link: link.link_id,
    )
    for link in selected:
        case = real_case(
            link,
            asks[link.ask_id],
            amendments[link.amendment_id],
            texts[asks[link.ask_id].document_id],
            source.articles,
            view.run_id,
            context_version=context_version,
        )
        size = len(request_bytes(build_request(case)))
        if size > MAX_REQUEST_BYTES:
            exclusions.append(
                {
                    "case_id": case.case_id,
                    "reason": "request_byte_bound",
                    "request_bytes": size,
                    "source": case.metadata,
                }
            )
        else:
            cases.append(case)
    source_hashes = {"atlas": ATLAS_SHA256}
    if context_version == "proposal-v2":
        source_hashes["collected_proposal_records"] = hashlib.sha256(
            "\n".join(
                a.model_dump_json() for a in source.articles if a.stage == "proposal"
            ).encode()
        ).hexdigest()
    trial = PreparedTrial(source_hashes=source_hashes, cases=cases)
    if output.exists() and PreparedTrial.model_validate_json(output.read_bytes()) != trial:
        raise ValueError("Refusing to overwrite different prepared inputs")
    write(output, trial)
    load_trial(output)
    summary: dict[str, object] = {
        "schema_version": "jev-real-preparation-1",
        "atlas_sha256": ATLAS_SHA256,
        "atlas_run_id": view.run_id,
        "inputs_sha256": digest(output),
        "selected": len(selected),
        "prepared": len(cases),
        "exclusions": exclusions,
        "source_status_counts": dict(Counter(link.status for link in selected)),
        "skipped_insufficient": len(view.bundle.links) - len(selected),
        "max_request_bytes": max(len(request_bytes(build_request(case))) for case in cases),
        "case_ids": [case.case_id for case in cases],
        "requests_sent": 0,
        "limitations": [
            "Selection uses the frozen candidate pool; this is not recall evaluation.",
            "Raw model judgements do not publish links; no human audit labels are supplied.",
            "Context retains the pilot limit: 1,200 preceding and 300 following characters.",
        ],
    }
    if context_version == "proposal-v2":
        summary.update(
            context_version=context_version,
            proposal_context_counts=dict(
                Counter(str(c.state["proposal_context_status"]) for c in cases)
            ),
            source_hashes=source_hashes,
            implementation_sha256=digest(Path(__file__)),
        )
    write(output.with_name(output.stem + "-preparation.json"), summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "case_ids"}))


def load_ledger(output: Path) -> Ledger:
    path = output / "ledger.json"
    return Ledger.model_validate_json(path.read_bytes()) if path.exists() else Ledger()


def charged(ledger: Ledger) -> float:
    return sum(
        e.actual_cost_usd
        if e.status == "complete" and e.actual_cost_usd is not None
        else e.reserved_usd
        for e in ledger.entries.values()
    )


def plan(
    trial: PreparedTrial, output: Path, max_cost: float, max_requests: int
) -> dict[str, object]:
    ledger = load_ledger(output)
    pending = {key_for(c): c for c in trial.cases if key_for(c) not in ledger.entries}
    sizes = [len(request_bytes(build_request(c))) for c in pending.values()]
    return {
        "model": MODEL,
        "cases": len(trial.cases),
        "uncalled_unique_requests": len(pending),
        "previous_attempts": len(ledger.entries),
        "accounted_cost_usd": charged(ledger),
        "per_request_reserved_usd": RESERVE_USD,
        "batch_worst_case_usd": len(pending) * RESERVE_USD,
        "payload_bytes": sum(sizes),
        "payload_bytes_as_tokens_cost_usd_not_guarantee": sum(sizes) * PRICE_PER_TOKEN,
        "max_cost_usd": max_cost,
        "max_requests": max_requests,
        "can_start_next": bool(pending)
        and len(ledger.entries) < max_requests
        and charged(ledger) + RESERVE_USD <= max_cost,
        "automatic_publication": False,
    }


def credential(path: Path) -> SecretStr:
    """Read only the explicitly supplied file; never execute it, echo it, or copy its key."""
    values: list[str] = []
    for line in path.read_text().splitlines():
        key, separator, value = line.removeprefix("export ").partition("=")
        if separator and key.strip() == "TYPESAFE_API_KEY":
            parts = shlex.split(value.strip(), comments=True)
            if len(parts) != 1:
                raise ValueError("Malformed TYPESAFE_API_KEY entry")
            values.append(parts[0])
    if len(values) != 1 or not values[0].strip():
        raise ValueError("Expected one nonempty TYPESAFE_API_KEY in the explicit env file")
    return SecretStr(values[0])


def run_trial(
    trial: PreparedTrial, output: Path, client: JevClient, max_cost: float, max_requests: int
) -> dict[str, object]:
    """Sequential single-operator execution; persist reservation before every network call."""
    ledger = load_ledger(output)
    stop = "complete"
    for case in trial.cases:
        key = key_for(case)
        if key in ledger.entries:
            continue  # Complete, pending and failed attempts are never automatically retried.
        if len(ledger.entries) >= max_requests:
            stop = "request_cap"
            break
        if charged(ledger) + RESERVE_USD > max_cost:
            stop = "cost_cap"
            break
        request = build_request(case)
        write(output / "requests" / f"{key}.json", request)
        ledger.entries[key] = Entry(
            case_id=case.case_id, status="pending", reserved_usd=RESERVE_USD
        )
        write(output / "ledger.json", ledger)
        began = perf_counter()
        try:
            response = client.evaluate(request.state, request.questions)
            cached = CachedResult(
                request_sha256=key,
                completed_at=datetime.now(UTC).isoformat(),
                elapsed_seconds=perf_counter() - began,
                response=response,
            )
            result_path = output / "results" / f"{key}.json"
            write(result_path, cached)
            ledger.entries[key] = Entry(
                case_id=case.case_id,
                status="complete",
                reserved_usd=RESERVE_USD,
                actual_cost_usd=response.usage.input_tokens * PRICE_PER_TOKEN,
                result_sha256=digest(result_path),
            )
        except Exception as error:
            # The transport's failure may still be charged. Keep its full reservation and
            # only the exception class: exception strings may contain request diagnostics.
            ledger.entries[key] = Entry(
                case_id=case.case_id,
                status="failed",
                reserved_usd=RESERVE_USD,
                error_type=type(error).__name__,
                elapsed_seconds=perf_counter() - began,
            )
            stop = "request_failed"
            write(output / "ledger.json", ledger)
            break
        write(output / "ledger.json", ledger)
        if charged(ledger) > max_cost:
            stop = "provider_usage_exceeded_reservation"
            break
    incomplete = [
        c.case_id
        for c in trial.cases
        if key_for(c) not in ledger.entries or ledger.entries[key_for(c)].status != "complete"
    ]
    return {
        "status": stop if stop != "complete" or not incomplete else "incomplete_previous_failure",
        "missing_cases": incomplete,
        "attempts": len(ledger.entries),
        "accounted_cost_usd": charged(ledger),
    }


def report(trial: PreparedTrial, output: Path, labels_path: Path) -> dict[str, object]:
    """Join diagnostics to labels only after inference; real pairs remain unlabelled."""
    ledger = load_ledger(output)
    labels: dict[str, str] = {}
    if any(c.family == "nli-v1" for c in trial.cases):
        if digest(labels_path) != trial.source_hashes.get("judge-labels.json"):
            raise ValueError("Diagnostic labels differ from frozen provenance")
        labels = cast(dict[str, dict[str, str]], json.loads(labels_path.read_bytes()))["labels"]
    rows: list[dict[str, object]] = []
    correct = answered = 0
    for case in trial.cases:
        key = key_for(case)
        entry = ledger.entries.get(key)
        if entry is None or entry.status != "complete":
            rows.append(
                {"case_id": case.case_id, "status": "not_called" if entry is None else entry.status}
            )
            continue
        path = output / "results" / f"{key}.json"
        if digest(path) != entry.result_sha256:
            raise ValueError("Cached result hash differs from the usage ledger")
        cached = CachedResult.model_validate_json(path.read_bytes())
        if cached.request_sha256 != key:
            raise ValueError("Cached response refers to another request")
        row: dict[str, object] = {
            "case_id": case.case_id,
            "family": case.family,
            "status": "complete",
            "response": cached.response.model_dump(mode="json"),
            "elapsed_seconds": cached.elapsed_seconds,
        }
        if case.family == "nli-v1":
            answer = cached.response.answers["relation"]
            if not isinstance(answer, ChoiceAnswer):
                raise ValueError("NLI diagnostic requires native Choice output")
            row.update(expected=labels[case.case_id], correct=answer.choice == labels[case.case_id])
            answered += 1
            correct += answer.choice == labels[case.case_id]
        rows.append(row)
    result: dict[str, object] = {
        "schema_version": "jev-gate3-report-1",
        "model": MODEL,
        "rows": rows,
        "diagnostic_answered": answered,
        "diagnostic_correct": correct,
        "local_nli_baseline": {"correct": 17, "total": 24},
        "baseline_comparable": answered == 24,
        "accounted_cost_usd": charged(ledger),
        "limitations": [
            "Synthetic intended relations are not representative legal accuracy.",
            "Real cases are selected diagnostics, not independent human audit labels.",
            "Four raw model judgements never activate publication or influence probabilities.",
        ],
    }
    write(output / "report.json", result)
    return {k: v for k, v in result.items() if k != "rows"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--atlas", type=Path, required=True)
    prepare_parser.add_argument(
        "--fixtures", type=Path, default=Path(__file__).parents[1] / "models/fixtures"
    )
    prepare_parser.add_argument("--out", type=Path, required=True)
    all_parser = commands.add_parser("prepare-all")
    all_parser.add_argument("--atlas", type=Path, required=True)
    all_parser.add_argument("--out", type=Path, required=True)
    all_parser.add_argument(
        "--context-version", choices=("proposal-v1", "proposal-v2"), default="proposal-v1"
    )
    for mode in ["run", "report"]:
        command = commands.add_parser(mode)
        command.add_argument("--inputs", type=Path, required=True)
        command.add_argument("--out", type=Path, required=True)
        if mode == "run":
            command.add_argument(
                "--execute",
                action="store_true",
                help="Explicitly enable provider requests; default is dry-run",
            )
            command.add_argument("--env-file", type=Path)
            command.add_argument("--max-cost-usd", type=float, default=0.05)
            command.add_argument("--max-requests", type=int, default=32)
        else:
            command.add_argument(
                "--labels",
                type=Path,
                default=Path(__file__).parents[1] / "models/fixtures/judge-labels.json",
            )
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.atlas, args.fixtures, args.out)
        return 0
    if args.mode == "prepare-all":
        prepare_all(args.atlas, args.out, context_version=args.context_version)
        return 0
    trial = load_trial(args.inputs)
    if args.mode == "report":
        print(json.dumps(report(trial, args.out, args.labels)))
        return 0
    if not 0 < args.max_cost_usd <= 1 or args.max_requests < 1:
        parser.error(
            "Cost cap must be positive and at most the authorized $1; request cap must be positive"
        )
    summary = plan(trial, args.out, args.max_cost_usd, args.max_requests)
    if not args.execute:
        print(json.dumps({"mode": "dry-run", **summary}))
        return 0
    if args.env_file is None:
        parser.error("Live execution requires an explicit --env-file")
    if not summary["can_start_next"]:
        ledger = load_ledger(args.out)
        complete = all(
            key_for(case) in ledger.entries and ledger.entries[key_for(case)].status == "complete"
            for case in trial.cases
        )
        status = "complete_cached" if complete else "no_request_budget_or_previous_failure"
        print(json.dumps({"status": status, **summary}))
        return 0 if complete else 2
    client = JevClient(credential(args.env_file), ssl.create_default_context())
    result = run_trial(trial, args.out, client, args.max_cost_usd, args.max_requests)
    print(json.dumps(result))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
