"""Experimental reworded associations targeted to exact accepted amendment/final runs.

BM25 retains its existing shortlist per amendment. Each candidate is judged separately
for every accepted occurrence, with the full old/new amendment and final provision. A
positive answer about some other amendment section never authorizes an adopted origin.
The 0.67 policy is uncalibrated; historical whole-amendment precision does not transfer.
"""

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from influence.schemas.atlas import Actor, Amendment, Ask
from influence.schemas.lineage import (
    AdoptionEvidence,
    AmendmentAdoption,
    OriginJudgment,
    OriginMatch,
    OriginSupport,
    TimeEligibility,
)
from influence.services.collected import Collected, PipelineError
from influence.services.jev import MODEL, JevRequest
from influence.services.jev_judge import (
    ADOPTED_PROMPT_REVISION,
    CUTOFF,
    JevAnswers,
    JevJudge,
    adopted_origin_request,
    proposal_articles,
    request_bytes,
)
from influence.services.lineage import evidence_id_of
from influence.services.lineage_candidates import asks_from_passages, find_candidates
from influence.services.prose_match import words_of

METHOD = "jev-reworded-origins"
METHOD_REVISION = ADOPTED_PROMPT_REVISION
_ELIGIBILITY: dict[bool | None, TimeEligibility] = {
    True: "ask_first",
    False: "amendment_first",
    None: "unknown_date",
}


@dataclass(frozen=True)
class _Target:
    key: str
    ask: Ask
    amendment: Amendment
    evidence: AdoptionEvidence


def reworded_origins(
    collected: Collected,
    adoptions: Sequence[AmendmentAdoption],
    judge: JevJudge,
    *,
    submitters: Mapping[str, Actor],
    known: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[tuple[OriginMatch, ...], str]:
    """Highest accepted candidate per document and exact evidence, with explicit diagnostics.

    `known` names eligible non-citation lexical (document, evidence) pairs. BM25 work is
    unchanged: linear indexing plus one bounded shortlist per amendment. Request expansion
    is O(C * E) per amendment for C candidates and E exact accepted evidence records;
    the cached judge asks each distinct request once, subject to its monetary cap.
    """
    skips: Counter[str] = Counter()
    carriers = {a.amendment_id: a for a in adoptions if a.kind == "verbatim"}
    sources = {a.amendment_id: a for a in collected.amendments}
    amendments: dict[str, Amendment] = {}
    for amendment_id, carrier in sorted(carriers.items()):
        if not carrier.evidence:
            skips["missing_carrier_evidence"] += 1
        elif amendment_id not in sources:
            skips["missing_amendment_source"] += 1
        else:
            amendments[amendment_id] = sources[amendment_id]
    asks = {ask.ask_id: ask for ask in asks_from_passages(collected.passages)}
    texts = {text.document_id: text.text for text in collected.document_texts}
    finals = {
        article.article_id: article
        for article in collected.articles
        if article.stage == "final_act"
    }
    proposal = proposal_articles(
        (article.provision, article.text)
        for article in collected.articles
        if article.stage == "proposal"
    )
    candidates = find_candidates((amendments[i] for i in sorted(amendments)), tuple(asks.values()))
    targets: list[_Target] = []
    requests: list[JevRequest] = []
    for candidate in candidates:
        ask, amendment = asks[candidate.ask_id], amendments[candidate.amendment_id]
        carrier = carriers[amendment.amendment_id]
        for evidence in sorted(carrier.evidence, key=lambda item: item.evidence_id):
            if evidence.phrase_id not in carrier.phrase_ids:
                raise PipelineError("Adopted origin evidence names a different carrier phrase")
            if (ask.document_id, evidence.evidence_id) in known:
                skips["already_lexical"] += 1
                continue
            prepared = adopted_origin_request(
                ask,
                amendment,
                evidence,
                texts.get(ask.document_id),
                finals.get(evidence.final_span.record_id),
                proposal,
            )
            if isinstance(prepared, str):
                skips[prepared] += 1
                continue
            key = hashlib.sha256(request_bytes(prepared)).hexdigest()
            targets.append(_Target(key, ask, amendment, evidence))
            requests.append(prepared)
    report = judge.run(requests)
    selected: dict[tuple[str, str], tuple[tuple[float, int, int, str], OriginMatch]] = {}
    for target in targets:
        answers = report.answers.get(target.key)
        if answers is None or answers.support < CUTOFF:
            continue
        identity = target.ask.document_id, target.evidence.evidence_id
        rank = (-answers.support, target.ask.span.start, target.ask.span.end, target.ask.ask_id)
        if identity not in selected or rank < selected[identity][0]:
            selected[identity] = rank, _origin(target, submitters, answers)
    diagnostics = ", ".join(f"{key}={skips[key]}" for key in sorted(skips)) or "none"
    budget = sum(reason.startswith("not asked:") for reason in report.failures.values())
    note = (
        f"Reworded origins ({METHOD}, {METHOD_REVISION}): Jev judged {len(report.answers)} of "
        f"{len({target.key for target in targets})} distinct adopted-target requests from "
        f"{len(candidates)} BM25 pairs for {len(amendments)} adopting amendment(s) "
        f"({report.cached} cached, {report.asked} asked, {budget} budget-skipped, "
        f"{len(report.failures) - budget} provider/answer failures, {report.spent_usd:.2f} USD; "
        f"unassessed: {diagnostics}); {len(selected)} cleared {CUTOFF} on all four "
        "directed support dimensions. "
        "This cutoff is an uncalibrated experimental policy, not measured accuracy or "
        "evidence of authorship or causal influence."
    )
    return tuple(selected[key][1] for key in sorted(selected)), note


def _origin(target: _Target, submitters: Mapping[str, Actor], answers: JevAnswers) -> OriginMatch:
    ask, amendment, evidence = target.ask, target.amendment, target.evidence
    submitter = submitters.get(ask.document_id)
    published, tabled = ask.submitted_at, amendment.tabled_on
    precedes = None if published is None or tabled is None else published.date() < tabled
    judgment = OriginJudgment(
        request_sha256=target.key,
        prompt_revision=ADOPTED_PROMPT_REVISION,
        model=MODEL,
        actual_request=answers.actual_request,
        same_legal_change=answers.same_legal_change,
        incompatible_legal_change=answers.incompatible_legal_change,
        shared_background=answers.shared_background,
        score=answers.support,
    )
    support = OriginSupport(
        support_id=evidence_id_of(
            "origin-support",
            evidence.evidence_id + ":" + target.key,
            (ask.span, evidence.amendment_span, evidence.final_span),
        ),
        kind="semantic",
        judgment=judgment,
        adoption_evidence_id=evidence.evidence_id,
        amendment_id=amendment.amendment_id,
        submission_span=ask.span,
        amendment_span=evidence.amendment_span,
        final_span=evidence.final_span,
    )
    return OriginMatch(
        phrase_id=evidence.phrase_id,
        document_id=ask.document_id,
        actor_id=ask.actor_id,
        organisation=None if submitter is None or submitter.kind == "citizens" else submitter.name,
        published_at=published,
        span=ask.span,
        kind="semantic",
        similarity=answers.support,
        words=len(words_of(ask.span.text)),
        amendment_ids=(amendment.amendment_id,),
        earliest_amendment_on=tabled,
        precedes=precedes,
        eligibility=_ELIGIBILITY[precedes],
        supports=(support,),
    )
