"""Batch fitted signals and explicitly audited publication; never invent missing evidence.

Audit provenance is supplied by the caller: disjoint identifiers detect accidental reuse,
not dishonest relabelling or group leakage. Real independent readers and upstream source
validation remain necessary. Context conflicts are English heuristics, not legal proof.
"""

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isclose, isfinite

from influence.schemas.atlas import (
    Amendment,
    Ask,
    Candidate,
    LinkAssessment,
    LinkTier,
    SourceSpan,
    span_matches,
)
from influence.schemas.scoring import TOKEN_PATTERN, ScoreRequest, TextChange
from influence.services.assessment import assess_link
from influence.services.audit import AuditReport, wilson_interval
from influence.services.calibration import FittedCombiner
from influence.services.masking import mask_quoted_law
from influence.services.passage_change import read_changes
from influence.services.ranking_signals import RankedPair, background_signals, feature_vector
from influence.services.scoring import changed_spans, score_pair
from influence.services.signals import SignalCorpus, pair_signals

METHOD = "atlas-fitted-signals-v2"


def model_digest(
    model: FittedCombiner,
    corpus: SignalCorpus,
    *,
    semantic_model: tuple[str, str] | None = None,
    entailment_model: tuple[str, str] | None = None,
    entailment_decision: str | None = None,
) -> str:
    """Bind audits/approval to fitted weights, corpus and every enabled model revision."""
    value = (
        METHOD,
        model.model_dump(mode="json"),
        corpus.fingerprint,
        semantic_model,
        entailment_model,
        entailment_decision,
    )
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def pair_digest(amendment: Amendment, ask: Ask, proposal_text: str | None = None) -> str:
    """Bind supplied semantic evidence to these exact records and their text versions."""
    value = json.dumps(
        (amendment.model_dump(mode="json"), ask.model_dump(mode="json"), proposal_text),
        sort_keys=True,
    )
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class SemanticEvidence:
    cosine: float
    model_id: str
    revision: str
    pair_digest: str


@dataclass(frozen=True)
class EntailmentEvidence:
    """An external, provenance-bound verdict with original source quotations."""

    supported: bool
    model_id: str
    revision: str
    pair_digest: str
    entailment_score: float
    contradiction_score: float
    neutral_score: float
    decision_revision: str
    amendment_spans: tuple[SourceSpan, ...]
    ask_spans: tuple[SourceSpan, ...]
    contradicted: bool = False


@dataclass(frozen=True)
class PublicationEvidence:
    """One tier's frozen cutoff and independently measured complete 95% Wilson audit.

    No defaults: the caller must explicitly supply its precision/sample requirement and
    attest which observations were used to fit, select the cutoff, and audit it. An audit
    is usable only at the exact audited cutoff, model, features and calculation revision.
    """

    cutoff: float
    audited_cutoff: float
    model_digest: str
    feature_names: tuple[str, ...]
    calculation_revision: str
    training_id: str
    development_id: str
    audit_id: str
    training_sample_ids: frozenset[str]
    development_sample_ids: frozenset[str]
    audit_sample_ids: frozenset[str]
    minimum_precision: float
    minimum_samples: int
    report: AuditReport


def _publication(
    tier: LinkTier, evidence: PublicationEvidence, model: FittedCombiner, digest: str
) -> None:
    ids = (evidence.training_id, evidence.development_id, evidence.audit_id)
    samples = (
        evidence.training_sample_ids,
        evidence.development_sample_ids,
        evidence.audit_sample_ids,
    )
    if (
        not all(value.strip() for value in ids)
        or len(set(ids)) != len(ids)
        or evidence.training_id != model.training_id
        or not all(samples)
        or any(not value.strip() for group in samples for value in group)
        or any(samples[i] & samples[j] for i in range(len(samples)) for j in range(i))
        or len(samples[0]) != model.training_samples
    ):
        raise ValueError(
            "Publication needs distinct training/development/audit provenance and samples"
        )
    if (
        evidence.model_digest != digest
        or evidence.feature_names != model.feature_names
        or evidence.calculation_revision != METHOD
    ):
        raise ValueError("Publication audit does not match the fitted model/features/calculation")
    if (
        not isfinite(evidence.cutoff)
        or not 0 <= evidence.cutoff <= 1
        or evidence.cutoff != evidence.audited_cutoff
        or not isfinite(evidence.minimum_precision)
        or not 0 < evidence.minimum_precision <= 1
        or type(evidence.minimum_samples) is not int
        or evidence.minimum_samples < 1
    ):
        raise ValueError(
            "Publication needs an exact audited cutoff and explicit precision/sample minima"
        )
    report = evidence.report
    if (
        any(
            type(count) is not int or count < 0
            for count in (
                report.sampled,
                report.resolved,
                report.correct,
                report.unresolved,
                report.unlabelled,
            )
        )
        or report.sampled != report.resolved
        or report.unresolved
        or report.unlabelled
        or report.resolved != len(samples[2])
        or report.correct > report.resolved
        or report.resolved < evidence.minimum_samples
        or dict(report.by_tier) != {tier: (report.correct, report.resolved)}
    ):
        raise ValueError("Publication requires a complete, sufficiently large audit of this tier")
    low, high = wilson_interval(report.correct, report.resolved)
    if (
        report.precision is None
        or not isclose(report.precision, report.correct / report.resolved)
        or not isclose(report.low, low)
        or not isclose(report.high, high)
        or low < evidence.minimum_precision
    ):
        raise ValueError(
            "Publication audit does not meet its verified Wilson precision requirement"
        )


def _semantic(evidence: SemanticEvidence | EntailmentEvidence, digest: str) -> None:
    if (
        not evidence.model_id.strip()
        or not evidence.revision.strip()
        or evidence.pair_digest != digest
    ):
        raise ValueError("Semantic evidence lacks model provenance or describes different inputs")


def _entailment_quotes(
    evidence: EntailmentEvidence, amendment: Amendment, ask: Ask, source: str
) -> None:
    if not evidence.amendment_spans or not evidence.ask_spans:
        raise ValueError("Entailment needs exact quotations on both sides")
    for span in evidence.amendment_spans:
        field = {"old_text": amendment.old_text, "new_text": amendment.new_text}.get(span.field)
        if (
            span.record_id != amendment.amendment_id
            or field is None
            or not span_matches(span, field)
        ):
            raise ValueError("Entailment amendment quote does not match its source")
    for span in evidence.ask_spans:
        if (
            span.record_id != ask.span.record_id
            or span.field != ask.span.field
            or span.start < ask.span.start
            or span.end > ask.span.end
            or not span_matches(span, source)
        ):
            raise ValueError("Entailment ask quote does not match its source")


def _copied(base: LinkAssessment, amendment: Amendment) -> bool:
    if amendment.old_text is None:
        return False
    changes = changed_spans(TextChange(old=amendment.old_text, new=amendment.new_text))
    return bool(changes) and all(
        any(
            quote.field == ("new_text" if change.operation == "insert" else "old_text")
            and quote.start <= change.start
            and quote.end >= change.end
            for quote in base.amendment_spans
        )
        for change in changes
    )


def calculate_links(
    candidates: Sequence[Candidate],
    *,
    amendments: Mapping[str, Amendment],
    asks: Mapping[str, Ask],
    source_texts: Mapping[str, str],
    corpus: SignalCorpus,
    combiner: FittedCombiner,
    publication: Mapping[LinkTier, PublicationEvidence],
    semantics: Mapping[str, SemanticEvidence] | None = None,
    entailment: Mapping[str, EntailmentEvidence] | None = None,
    semantic_model: tuple[str, str] | None = None,
    entailment_model: tuple[str, str] | None = None,
    entailment_decision: str | None = None,
    approved_model_digests: frozenset[str] = frozenset(),
    proposal_texts: Mapping[str, str] | None = None,
) -> tuple[LinkAssessment, ...]:
    """Assess every alternative with frozen fitted weights and law-local background signals.

    O(N log N + N*T²) for N bounded candidates and <=800 tokens per text; quoted reading
    alternatives and changed-clause comparisons add the costs documented in signals.py.
    All candidates supplied for a law define its background: this is not a corpus-wide
    distribution unless the caller supplied that pool. No threshold or missing feature
    is substituted. Cosine alone never establishes reworded entailment. Unknown source
    originals use the existing lexical passage compatibility mode, explicitly flagged.
    """
    digest = model_digest(
        combiner,
        corpus,
        semantic_model=semantic_model,
        entailment_model=entailment_model,
        entailment_decision=entailment_decision,
    )
    approved = digest in approved_model_digests
    for tier, policy in publication.items():
        _publication(tier, policy, combiner, digest)
    candidate_ids = {candidate.candidate_id for candidate in candidates}
    if len(candidate_ids) != len(candidates):
        raise ValueError("Candidate IDs must be unique")
    semantic_rows, entailment_rows = semantics or {}, entailment or {}
    if (set(semantic_rows) | set(entailment_rows)) - candidate_ids:
        raise ValueError("Semantic evidence refers to an absent candidate")
    bases: dict[str, LinkAssessment] = {}
    feature_rows: dict[str, dict[str, float]] = {}
    pools: dict[str, list[RankedPair]] = defaultdict(list)
    for candidate in candidates:
        amendment, ask = amendments[candidate.amendment_id], asks[candidate.ask_id]
        if (
            amendment.amendment_id != candidate.amendment_id
            or ask.ask_id != candidate.ask_id
            or ask.procedure_id != candidate.procedure_id
            or amendment.procedure_id != candidate.procedure_id
        ):
            raise ValueError("Candidate joins inconsistent IDs or procedures")
        source = source_texts[ask.span.record_id]
        if (
            ask.span.record_id not in {ask.document_id, ask.passage_id}
            or ask.span.field != "text"
            or not span_matches(ask.span, source)
        ):
            raise ValueError("Ask quote does not match its declared source")
        readings = read_changes(ask.span.text)
        if not readings:
            raise ValueError("Ask has no usable change or statement")
        base = assess_link(
            amendment, ask, source, candidate_id=candidate.candidate_id, publishable=frozenset()
        )
        amendment_change = TextChange(old=amendment.old_text or "", new=amendment.new_text)
        reading = max(
            readings,
            key=lambda row: (
                score_pair(
                    ScoreRequest(
                        amendment=amendment_change,
                        submission=TextChange(old=row.old or "", new=row.new),
                    )
                ).score
            ),
        )
        masked = (
            mask_quoted_law(
                reading.new,
                (proposal_texts or {}).get(candidate.procedure_id, amendment.old_text or ""),
            )
            if reading.old is None
            else mask_quoted_law(reading.new, "")
        )
        # An all-masked passage is a zero edit, not an invented insertion or blank input.
        remaining_words = any(token.isalnum() for token in TOKEN_PATTERN.findall(masked.text))
        submission_change = (
            TextChange(old=reading.old or "", new=masked.text)
            if remaining_words or reading.old
            else TextChange(old=reading.new, new=reading.new)
        )
        quote_origin = ask.span.start + reading.start
        copied_quotes_unmasked = not any(
            quote.start < quote_origin + end and quote.end > quote_origin + start
            for quote in base.ask_spans
            for start, end in masked.spans
        )
        signals = {
            **base.signals,
            **pair_signals(amendment_change, submission_change, corpus),
            "submission_original_known": float(reading.old is not None),
            "amendment_original_known": float(amendment.old_text is not None),
            "retrieval_score": candidate.retrieval_score,
            "quoted_law_masked_chars": float(sum(end - start for start, end in masked.spans)),
            "copied_quotes_unmasked": float(copied_quotes_unmasked),
            "submission_fully_masked": float(bool(masked.spans) and not remaining_words),
        }
        inputs_digest = pair_digest(
            amendment, ask, (proposal_texts or {}).get(candidate.procedure_id)
        )
        if semantic := semantic_rows.get(candidate.candidate_id):
            _semantic(semantic, inputs_digest)
            if (semantic.model_id, semantic.revision) != semantic_model:
                raise ValueError(
                    "Semantic model does not match the frozen calculation configuration"
                )
            if not isfinite(semantic.cosine) or not -1 <= semantic.cosine <= 1:
                raise ValueError("Semantic cosine must be finite and within [-1,1]")
            signals["semantic_cosine"] = semantic.cosine
        if entailed := entailment_rows.get(candidate.candidate_id):
            _semantic(entailed, inputs_digest)
            if (entailed.model_id, entailed.revision) != entailment_model:
                raise ValueError(
                    "Entailment model does not match the frozen calculation configuration"
                )
            scores = (
                entailed.entailment_score,
                entailed.contradiction_score,
                entailed.neutral_score,
            )
            if (
                type(entailed.supported) is not bool
                or type(entailed.contradicted) is not bool
                or (entailed.supported and entailed.contradicted)
                or not entailed.decision_revision.strip()
                or entailed.decision_revision != entailment_decision
                or any(not isfinite(score) or not 0 <= score <= 1 for score in scores)
                or not isclose(sum(scores), 1.0, abs_tol=1e-6)
            ):
                raise ValueError(
                    "Judge scores/decision do not match the frozen calculation configuration"
                )
            signals.update(
                entailment_score=entailed.entailment_score,
                contradiction_score=entailed.contradiction_score,
                neutral_score=entailed.neutral_score,
            )
            _entailment_quotes(entailed, amendment, ask, source)
        bases[candidate.candidate_id] = base
        feature_rows[candidate.candidate_id] = signals
        pools[candidate.procedure_id].append(
            RankedPair(
                candidate.candidate_id,
                candidate.amendment_id,
                candidate.ask_id,
                signals["lexical_overlap"],
            )
        )
    for pool in pools.values():
        for identifier, signals in background_signals(pool).items():
            feature_rows[identifier].update(signals)
    results: list[LinkAssessment] = []
    for candidate in sorted(candidates, key=lambda row: row.candidate_id):
        identifier = candidate.candidate_id
        base, signals = bases[identifier], feature_rows[identifier]
        support = combiner.score(feature_vector(signals, combiner.feature_names))
        signals["model_support"] = support
        signals["development_only"] = float(not approved)
        limits = list(base.limitations)
        input_hash = pair_digest(
            amendments[candidate.amendment_id],
            asks[candidate.ask_id],
            (proposal_texts or {}).get(candidate.procedure_id),
        )
        limits.append(f"Calculation input digest: {input_hash}.")
        if not approved:
            limits.append(
                "Development-only fitted artifact: no accepted approval; publication disabled."
            )
        limits.append(
            "Fitted sigmoid is support, not a calibrated influence probability; "
            "backgrounds use the supplied law candidate pool."
        )
        if not signals["submission_original_known"]:
            limits.append(
                "Submission is ordinary prose with unknown original; "
                "lexical passage compatibility is not a known insertion."
            )
        if signals["quoted_law_masked_chars"]:
            limits.append(
                "Known proposal quotations masked from ordinary-prose features; "
                "original quotes retained."
            )
        if semantic := semantic_rows.get(identifier):
            limits.append(f"Semantic cosine: {semantic.model_id}@{semantic.revision}.")
        entailed = entailment_rows.get(identifier)
        conflict = (
            (entailed is not None and entailed.contradicted)
            or base.status == "contradicted"
            or any(
                signals[key] for key in ("negation_conflict", "modal_conflict", "quantity_conflict")
            )
        )
        tier: LinkTier | None = None
        amendment_quotes, ask_quotes = base.amendment_spans, base.ask_spans
        if (
            not signals["short_edit"]
            and signals["copied_quotes_unmasked"]
            and signals["rare_phrase_overlap"]
            and any(
                sum(token.isalnum() for token in TOKEN_PATTERN.findall(quote.text)) >= 6
                for quote in base.amendment_spans
            )
            and _copied(base, amendments[candidate.amendment_id])
            and ask_quotes
        ):
            tier = "copied"
        elif entailed is not None and entailed.supported:
            tier = "reworded"
            amendment_quotes, ask_quotes = entailed.amendment_spans, entailed.ask_spans
            limits.append(f"Entailment evidence: {entailed.model_id}@{entailed.revision}.")
        elif signals["same_direction"] and amendment_quotes and ask_quotes:
            tier = "same_direction"
        else:
            limits.append(
                "No full copied change or explicit supporting entailment evidence; "
                "reworded status is unavailable."
            )
        policy = publication.get(tier) if tier is not None else None
        eligible = (
            approved
            and tier in {"copied", "reworded"}
            and (entailed is None or entailed.supported)
            and not signals["submission_fully_masked"]
            and base.time_eligibility == "ask_first"
            and amendments[candidate.amendment_id].old_text is not None
            and (not signals["short_edit"] or tier == "reworded")
        )
        if conflict:
            limits.append(
                "Conservative English cue or supplied entailment veto; "
                "not a finding of legal contradiction."
            )
        elif policy is None:
            limits.append(
                "This tier has no matching independent publication audit and frozen cutoff."
            )
        else:
            limits.append(
                f"Publication evidence: development {policy.development_id}; "
                f"audit {policy.audit_id}; cutoff {policy.cutoff}."
            )
        status = (
            "contradicted"
            if conflict
            else "insufficient_evidence"
            if tier is None
            else (
                "published"
                if policy is not None
                and support >= policy.cutoff
                and eligible
                and amendment_quotes
                and ask_quotes
                else "unconfirmed"
            )
        )
        results.append(
            LinkAssessment(
                link_id=f"link:calculation:{hashlib.sha256(identifier.encode()).hexdigest()}",
                procedure_id=candidate.procedure_id,
                candidate_id=identifier,
                amendment_id=candidate.amendment_id,
                ask_id=candidate.ask_id,
                status=status,
                tier=None if conflict else tier,
                support_score=0.0 if conflict else support,
                signals=signals,
                amendment_spans=amendment_quotes,
                ask_spans=ask_quotes,
                time_eligibility=base.time_eligibility,
                method=METHOD,
                method_revision=digest,
                limitations=tuple(limits),
            )
        )
    return tuple(results)
