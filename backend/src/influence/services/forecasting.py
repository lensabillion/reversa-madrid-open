"""Part 7, NEXT: forecasts for the open asks of named laws, from every written atlas view.

History is every ask of a completed law whose final-act outcome was decided (full or partial
is a win, not observed a loss; unknown is left out), with features dated before the law's
completion: the law's first subject, the asking actor's kind and how many amendments carry
the ask through a published or unconfirmed link. Targets are the asks of the named laws
that are still open. `services/forecast.py` validates on rolling time splits and publishes a
number only when the model beats prevalence; otherwise each forecast is a reasoned scenario
with no score, and the reasons say how much history there was.

The plan's labelled fallback, "the rapporteur's draft includes the ask", needs the
rapporteur's draft report text. The collect step records the rapporteurs' names from
Parltrack but fetches no draft report, so the rule is reported as not computable rather
than approximated.
"""

from collections import Counter
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time
from pathlib import Path

from pydantic import ValidationError

from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import procedure_slug
from influence.schemas.atlas import ActorKind, Forecast, LawRecord, OutcomeResult
from influence.schemas.atlas_view import AtlasView
from influence.schemas.forecast_view import (
    FallbackRule,
    ForecastLaw,
    ForecastValidation,
    ForecastView,
)
from influence.services.forecast import (
    EVENT,
    MODEL_REVISION,
    Example,
    Features,
    Validation,
    forecast_ask,
    validate,
)
from influence.services.law_query import LAW_ALIASES, parse_query, resolve_title
from influence.services.pipeline import TRACED_STATUSES, VIEW_FILE

FORECAST_FILE = "forecast.json"
HORIZON = "The law's final act"
BLOCKS = 4
DECIDED = frozenset({"full", "partial", "not_observed"})
WON = frozenset({"full", "partial"})
# Several final-act outcomes for one ask keep the strongest: a win anywhere is a win.
_RANK: dict[OutcomeResult, int] = {"unknown": 0, "not_observed": 1, "partial": 2, "full": 3}
RAPPORTEUR_DRAFT = FallbackRule(
    rule="rapporteur_draft",
    computable=False,
    reason=(
        "The rule asks whether the rapporteur's draft report includes the ask. Parltrack "
        "gives the rapporteurs' names, but the collect step fetches no draft report text, so "
        "the rule cannot be computed from our data and no rule score is published."
    ),
)
LIMITATIONS = (
    "Only asks with a published or unconfirmed link to an amendment are traced to the final "
    "act, so the history holds no ask that no amendment carried; that group falls back to "
    "the overall rate.",
    "Features are the law's first subject, the asking actor's kind and the number of "
    "amendments carrying the ask. An example is used only when the ask and every amendment "
    "carrying it are dated before the law's completion date.",
    "Rolling splits order asks by their law's completion date and never put one law on both "
    "sides, so a handful of laws gives a handful of testable splits at most.",
)


class ForecastError(Exception):
    """A named law has no atlas view, or the name matches none or several."""


@dataclass(frozen=True, slots=True)
class AskEvidence:
    """What the atlas view says about one ask: its dates and its final-act result."""

    ask_id: str
    actor_kind: ActorKind | None
    submitted_at: datetime | None
    # Tabling dates of the amendments carrying the ask; None where a date is unknown.
    amendment_dates: tuple[date | None, ...]
    final: OutcomeResult | None


@dataclass(frozen=True, slots=True)
class LawEvidence:
    slug: str
    law: LawRecord
    generated_at: datetime
    asks: tuple[AskEvidence, ...]


def evidence_from_view(view: AtlasView) -> LawEvidence | None:
    """The forecast's inputs from one view; None when it holds no record of its own law.

    Linear in the view's records.
    """
    laws = {law.procedure_id: law for law in view.bundle.laws}
    law = laws.get(view.procedure_id)
    if law is None:
        return None
    kinds: dict[str, ActorKind] = {actor.actor_id: actor.kind for actor in view.bundle.actors}
    tabled = {amendment.amendment_id: amendment.tabled_on for amendment in view.bundle.amendments}
    carried: dict[str, set[str]] = {}
    for link in view.bundle.links:
        if link.status in TRACED_STATUSES:
            carried.setdefault(link.ask_id, set()).add(link.amendment_id)
    finals: dict[str, list[OutcomeResult]] = {}
    for outcome in view.bundle.outcomes:
        if outcome.stage == "final_act":
            finals.setdefault(outcome.ask_id, []).append(outcome.result)
    asks = tuple(
        AskEvidence(
            ask_id=ask.ask_id,
            actor_kind=kinds.get(ask.actor_id),
            submitted_at=ask.submitted_at,
            amendment_dates=tuple(tabled.get(i) for i in sorted(carried.get(ask.ask_id, ()))),
            final=max(finals.get(ask.ask_id, ()), key=_RANK.__getitem__, default=None),
        )
        for ask in view.bundle.asks
    )
    return LawEvidence(view.slug, law, view.generated_at, asks)


def read_evidence(data_root: Path) -> tuple[tuple[LawEvidence, ...], tuple[str, ...]]:
    """Every law with a readable view under `data_root/laws`, and why any other was skipped.

    One broken view does not stop the forecast: it is named in the problems instead.
    """
    laws: list[LawEvidence] = []
    problems: list[str] = []
    for path in sorted((data_root / "laws").glob(f"*/{VIEW_FILE}")):
        try:
            view = AtlasView.model_validate_json(path.read_bytes())
        except ValidationError as error:
            count = error.error_count()
            problems.append(f"{path.parent.name}: the view is invalid ({count} errors)")
            continue
        evidence = evidence_from_view(view)
        if evidence is None:
            problems.append(f"{path.parent.name}: the view holds no record of its own law")
            continue
        laws.append(evidence)
    return tuple(laws), tuple(problems)


def resolve_law(query: str, laws: Sequence[LawRecord]) -> LawRecord:
    """The law a slug, procedure number, CELEX, COM reference, common name or title names.

    Only laws with a written view are searched; `make atlas` writes one.
    """
    trimmed = query.strip()
    by_slug = [law for law in laws if procedure_slug(law.procedure_id) == trimmed]
    if by_slug:
        return by_slug[0]
    try:
        parsed = parse_query(query)
    except ValueError as error:
        raise ForecastError(str(error)) from error
    if parsed.kind == "procedure":
        found = [law for law in laws if law.procedure_id == parsed.value]
    elif parsed.kind == "celex":
        found = [law for law in laws if parsed.value in (law.celex_proposal, law.celex_final)]
    elif parsed.kind == "com":
        found = [law for law in laws if law.com_reference == parsed.value]
    else:
        resolution = resolve_title(
            parsed.value, ((law.procedure_id, law.title) for law in laws), LAW_ALIASES
        )
        if resolution.ambiguous:
            names = "; ".join(f"{c.procedure_id} {c.title}" for c in resolution.candidates)
            raise ForecastError(f"{query!r} names more than one law with a view: {names}")
        chosen = resolution.chosen
        found = (
            []
            if chosen is None
            else [law for law in laws if law.procedure_id == chosen.procedure_id]
        )
    if not found:
        raise ForecastError(
            f"No atlas view matches {query!r}; run `make atlas LAW='{query}'` first"
        )
    return found[0]


def _start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _features(law: LawEvidence, ask: AskEvidence) -> tuple[Features, bool]:
    """The ask's features and whether every date they rest on is known."""
    subject = law.law.subjects[0] if law.law.subjects else None
    undated_amendment = None in ask.amendment_dates
    checks = (
        ("law_subject", subject is None),
        ("actor_kind", ask.actor_kind is None),
        ("ask_date", ask.submitted_at is None),
        ("amendment_date", undated_amendment),
    )
    dates = [_start(day) for day in ask.amendment_dates if day is not None]
    if ask.submitted_at is not None:
        dates.append(ask.submitted_at)
    features = Features(
        topic=f"{subject or 'subject unknown'} | {ask.actor_kind or 'actor kind unknown'}",
        amendment_count=len(ask.amendment_dates),
        # An open ask with no date at all was known by the time its view was built.
        observed_at=max(dates, default=law.generated_at),
        missing=tuple(name for name, absent in checks if absent),
    )
    return features, ask.submitted_at is not None and not undated_amendment


def _training_problem(
    ask: AskEvidence, features: Features, dated: bool, decided: datetime
) -> str | None:
    if ask.final is None:
        return "no final-act outcome traced"
    if ask.final == "unknown":
        return "final-act outcome unknown"
    if not dated:
        return "features undated"
    if features.observed_at >= decided:
        return "features not observed before the decision"
    return None


@dataclass
class _Tally:
    excluded: Counter[str]
    trained: int = 0
    forecasts: int = 0


def _validation_record(validation: Validation, examples: Sequence[Example]) -> ForecastValidation:
    return ForecastValidation(
        blocks=BLOCKS,
        training_laws=len({item.procedure_id for item in examples}),
        training_examples=len(examples),
        training_wins=sum(item.won for item in examples),
        splits=validation.splits,
        tested_splits=validation.tested_splits,
        test_examples=validation.test_examples,
        model_auc=validation.model_auc,
        baseline_auc=validation.baseline_auc,
        model_brier=validation.model_brier,
        baseline_brier=validation.baseline_brier,
        adequate=validation.adequate,
        reasons=validation.reasons,
    )


def _note(law: LawRecord, target: bool) -> str | None:
    if not target or law.status in ("ongoing", "unknown"):
        return None
    if law.status == "completed":
        return "Completed: its decided asks are history, not forecast targets."
    return "Withdrawn: there is no later stage to forecast."


def build_forecasts(
    laws: Sequence[LawEvidence],
    targets: Collection[str],
    *,
    generated_at: datetime,
    problems: Iterable[str] = (),
) -> ForecastView:
    """Validate on the completed laws' history, then forecast the targets' open asks.

    `targets` are slugs. Every forecast is made as of `generated_at` from history decided
    before it; LeakageError is raised if any input is dated later. O(T * H) for T target
    asks and H history examples, since each forecast refits the group rates on its history.
    """
    examples: list[Example] = []
    pending: list[tuple[LawEvidence, AskEvidence, Features]] = []
    tallies: dict[str, _Tally] = {}
    for law in laws:
        tally = tallies[law.slug] = _Tally(Counter())
        record = law.law
        decided = _start(record.completed_on) if record.completed_on is not None else None
        for ask in law.asks:
            features, dated = _features(law, ask)
            if record.status == "completed":
                if decided is None:
                    tally.excluded["completion date unknown"] += 1
                    continue
                problem = _training_problem(ask, features, dated, decided)
                if problem is not None:
                    tally.excluded[problem] += 1
                    continue
                examples.append(Example(record.procedure_id, features, decided, ask.final in WON))
                tally.trained += 1
            elif record.status == "withdrawn":
                tally.excluded["law withdrawn"] += 1
            elif law.slug not in targets:
                tally.excluded["open law not named as a target"] += 1
            elif ask.final in DECIDED:
                tally.excluded["final-act outcome already decided"] += 1
            else:
                pending.append((law, ask, features))
    validation = validate(examples, BLOCKS)
    if not validation.adequate:
        history_laws = len({item.procedure_id for item in examples})
        validation = replace(
            validation,
            reasons=(
                *validation.reasons,
                f"The history holds {len(examples)} decided asks from {history_laws} "
                "completed law(s); a number needs more laws than that.",
            ),
        )
    history = [item for item in examples if item.decided_at < generated_at]
    forecasts: list[Forecast] = []
    for law, ask, features in pending:
        forecasts.append(
            forecast_ask(
                ask_id=ask.ask_id,
                procedure_id=law.law.procedure_id,
                as_of=generated_at,
                features=features,
                history=history,
                validation=validation,
                horizon=HORIZON,
            )
        )
        tallies[law.slug].forecasts += 1
    return ForecastView(
        generated_at=generated_at,
        as_of=generated_at,
        model_revision=MODEL_REVISION,
        event=EVENT,
        horizon=HORIZON,
        laws=tuple(
            ForecastLaw(
                slug=law.slug,
                procedure_id=law.law.procedure_id,
                title=law.law.title,
                status=law.law.status,
                completed_on=law.law.completed_on,
                target=law.slug in targets,
                asks=len(law.asks),
                training_examples=tallies[law.slug].trained,
                forecasts=tallies[law.slug].forecasts,
                excluded=dict(sorted(tallies[law.slug].excluded.items())),
                note=_note(law.law, law.slug in targets),
            )
            for law in laws
        ),
        validation=_validation_record(validation, examples),
        fallback_rule=RAPPORTEUR_DRAFT,
        forecasts=tuple(sorted(forecasts, key=lambda item: (item.procedure_id, item.ask_id))),
        limitations=(
            *LIMITATIONS,
            *(f"Skipped view {problem}." for problem in problems),
        ),
    )


def write_forecasts(view: ForecastView, data_root: Path) -> Path:
    path = data_root / "laws" / FORECAST_FILE
    write_bytes_atomic(path, view.model_dump_json(by_alias=True, indent=2).encode("utf-8"))
    return path
