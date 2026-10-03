"""Lineage, reworded origins: consultation passages Jev judges to ask for an adopted change.

Verbatim origins (`services/origin.py`) need a run of the adopted wording itself in the
document. Organisations mostly ask in their own words: on the AI Act verbatim search finds
a few dozen documents among 788. This covers the reworded case for the amendments whose
wording reached the final act:

1. For each adopting amendment, part 3's BM25 (`pipeline.find_candidates`) shortlists the
   consultation passages that share its rare changed words.
2. Each (passage, amendment) pair goes to Jev with PR #63's frozen prompt
   (`jev_judge.judge_request`); answers are cached by request and the spend is capped.
3. A pair whose four answers all clear `jev_judge.CUTOFF` (the weakest answer, read in the
   direction that supports a link, is `JevAnswers.support`) becomes an `OriginMatch` of
   kind "semantic": the whole passage is quoted, `similarity` holds that support, and the
   dates decide `precedes` as for a verbatim origin. A pair already found word for word is
   not repeated.

Jev's answers say a request and an amendment make the same legal change; they are not
proof that one caused the other. BM25 bounds what Jev sees: a request with none of the
amendment's rare words is never judged (BM25 recall@5 is 0.663 on LobbyPlag's verified
pairs). The cost is one Jev call per distinct pair, about 5 per adopting amendment.
"""

import hashlib
from collections.abc import Mapping, Sequence

from influence.schemas.atlas import Actor, Amendment, Ask
from influence.schemas.lineage import AmendmentAdoption, OriginMatch, TimeEligibility
from influence.services.jev import JevRequest
from influence.services.jev_judge import (
    CUTOFF,
    JevJudge,
    judge_request,
    proposal_articles,
    request_bytes,
)
from influence.services.pipeline import Collected, asks_from_passages, find_candidates
from influence.services.prose_match import words_of

METHOD = "jev-reworded-origins"
_ELIGIBILITY: dict[bool | None, TimeEligibility] = {
    True: "ask_first",
    False: "amendment_first",
    None: "unknown_date",
}


def reworded_origins(
    collected: Collected,
    adoptions: Sequence[AmendmentAdoption],
    judge: JevJudge,
    *,
    submitters: Mapping[str, Actor],
    known: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[tuple[OriginMatch, ...], str]:
    """Semantic origins for the adopting amendments, and one sentence on what Jev did.

    `known` holds the (document, amendment) pairs verbatim search already found. The
    shortlist is linear in the passages' length plus one BM25 search per amendment; the
    judge makes at most one call per distinct request.
    """
    phrase_of = {a.amendment_id: a.phrase_ids[0] for a in adoptions if a.kind == "verbatim"}
    amendments = {a.amendment_id: a for a in collected.amendments if a.amendment_id in phrase_of}
    asks = {ask.ask_id: ask for ask in asks_from_passages(collected.passages)}
    texts = {text.document_id: text.text for text in collected.document_texts}
    proposal = proposal_articles(
        (article.provision, article.text)
        for article in collected.articles
        if article.stage == "proposal"
    )
    candidates = find_candidates((amendments[i] for i in sorted(amendments)), tuple(asks.values()))
    pairs: list[tuple[str, str, str]] = []  # (request key, ask id, amendment id)
    requests: list[JevRequest] = []
    unjudgeable = 0
    for candidate in candidates:
        ask = asks[candidate.ask_id]
        if (ask.document_id, candidate.amendment_id) in known or ask.document_id not in texts:
            continue
        request = judge_request(
            ask, amendments[candidate.amendment_id], texts[ask.document_id], proposal
        )
        if request is None:
            unjudgeable += 1
            continue
        key = hashlib.sha256(request_bytes(request)).hexdigest()
        pairs.append((key, ask.ask_id, candidate.amendment_id))
        requests.append(request)
    report = judge.run(requests)

    found: dict[tuple[str, str], OriginMatch] = {}
    for key, ask_id, amendment_id in pairs:
        answers = report.answers.get(key)
        ask = asks[ask_id]
        if answers is None or answers.support < CUTOFF:
            continue
        if (ask.document_id, amendment_id) in found:
            continue
        found[ask.document_id, amendment_id] = _origin(
            ask, amendments[amendment_id], phrase_of[amendment_id], submitters, answers.support
        )
    note = (
        f"Reworded origins ({METHOD}): Jev judged {len(report.answers)} of {len(set(pairs))} "
        f"distinct BM25 pairs for {len(amendments)} adopting amendment(s) "
        f"({report.cached} cached, {len(report.failures)} not judged, {unjudgeable} over the "
        f"request bound, {report.spent_usd:.2f} USD); {len(found)} cleared {CUTOFF} on all "
        "four answers. Jev's answers are evidence of the same legal change, not of authorship."
    )
    return tuple(sorted(found.values(), key=lambda o: (o.document_id, o.amendment_ids))), note


def _origin(
    ask: Ask,
    amendment: Amendment,
    phrase_id: str,
    submitters: Mapping[str, Actor],
    support: float,
) -> OriginMatch:
    submitter = submitters.get(ask.document_id)
    published = ask.submitted_at
    tabled = amendment.tabled_on
    precedes = None if published is None or tabled is None else published.date() < tabled
    return OriginMatch(
        phrase_id=phrase_id,
        document_id=ask.document_id,
        actor_id=ask.actor_id,
        organisation=None if submitter is None or submitter.kind == "citizens" else submitter.name,
        published_at=published,
        span=ask.span,
        kind="semantic",
        similarity=support,
        words=len(words_of(ask.span.text)),
        amendment_ids=(amendment.amendment_id,),
        earliest_amendment_on=tabled,
        precedes=precedes,
        eligibility=_ELIGIBILITY[precedes],
    )
