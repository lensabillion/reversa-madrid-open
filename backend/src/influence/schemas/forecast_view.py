"""Part 7, NEXT: what `influence forecast` writes to `data/laws/forecast.json`.

Every forecast carries the validation that decided whether it may hold a number. When the
rolling-split validation does not beat the prevalence baseline, every forecast is a reasoned
scenario with no score, and `validation.reasons` says why.
"""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, Field

from influence.schemas.atlas import Forecast, LawStatus, NonEmpty, ProcedureId
from influence.schemas.atlas_view import Slug
from influence.schemas.scoring import FrozenModel

FORECAST_VIEW_VERSION = "forecast-view-1"


class ForecastLaw(FrozenModel):
    """One law read: as training history, as a forecast target, or both, with its counts."""

    slug: Slug
    procedure_id: ProcedureId
    title: NonEmpty
    status: LawStatus
    completed_on: date | None
    target: bool
    asks: int = Field(ge=0)
    training_examples: int = Field(ge=0)
    forecasts: int = Field(ge=0)
    # Why asks of this law were neither trained on nor forecast, with how many each.
    excluded: dict[str, int]
    note: str | None = None


class ForecastValidation(FrozenModel):
    """The rolling-split comparison of the group-rate model with the prevalence baseline."""

    blocks: int = Field(ge=1)
    training_laws: int = Field(ge=0)
    training_examples: int = Field(ge=0)
    training_wins: int = Field(ge=0)
    splits: int = Field(ge=0)
    tested_splits: int = Field(ge=0)
    test_examples: int = Field(ge=0)
    model_auc: float | None
    baseline_auc: float | None
    model_brier: float | None
    baseline_brier: float | None
    adequate: bool
    reasons: tuple[str, ...]


class FallbackRule(FrozenModel):
    """The plan's labelled fallback, and whether our collected data can compute it."""

    rule: Literal["rapporteur_draft"]
    computable: bool
    reason: NonEmpty


class ForecastView(FrozenModel):
    schema_version: Literal["forecast-view-1"] = FORECAST_VIEW_VERSION
    generated_at: AwareDatetime
    as_of: AwareDatetime
    model_revision: NonEmpty
    event: NonEmpty
    horizon: NonEmpty
    laws: tuple[ForecastLaw, ...]
    validation: ForecastValidation
    fallback_rule: FallbackRule
    forecasts: tuple[Forecast, ...]
    limitations: tuple[str, ...]
