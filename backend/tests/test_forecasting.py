"""Part 7, NEXT: the forecast command over written atlas views.

History comes only from completed laws with a decided final-act outcome and features dated
before the decision; targets are the named open laws' undecided asks. A number appears only
when rolling-split validation beats prevalence; with few laws every forecast is a scenario.
"""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from atlas_fixture import LAW_A, build_fixture
from test_pipeline import matching_world

from influence import cli
from influence.extraction.layout import procedure_slug
from influence.schemas.atlas import ActorKind, LawRecord, LawStatus, OutcomeResult
from influence.schemas.atlas_view import AtlasBundleView, AtlasView
from influence.schemas.forecast_view import ForecastView
from influence.services import pipeline
from influence.services.forecast import LeakageError
from influence.services.forecasting import (
    FORECAST_FILE,
    AskEvidence,
    ForecastError,
    LawEvidence,
    build_forecasts,
    evidence_from_view,
    read_evidence,
    resolve_law,
    write_forecasts,
)

NOW = datetime(2099, 12, 31, tzinfo=UTC)
FIRST = date(2090, 1, 1)


def _record(
    number: int,
    status: LawStatus = "completed",
    completed_on: date | None = None,
    subjects: tuple[str, ...] = ("3.40 Industry",),
) -> LawRecord:
    return LawRecord(
        procedure_id=f"2090/{number:04d}(COD)",
        title=f"Fixture regulation number {number} on widgets",
        status=status,
        celex_proposal=f"5209{number}PC0001",
        com_reference=f"COM(2090){number}",
        subjects=subjects,
        completed_on=completed_on,
        coverage=(),
    )


def _ask(
    key: str,
    final: OutcomeResult | None,
    kind: ActorKind | None = "organisation",
    submitted: date | None = FIRST,
    tabled: tuple[date | None, ...] = (FIRST + timedelta(days=1),),
) -> AskEvidence:
    return AskEvidence(
        ask_id=f"ask:{key}",
        actor_kind=kind,
        submitted_at=None
        if submitted is None
        else datetime.combine(submitted, datetime.min.time(), UTC),
        amendment_dates=tabled,
        final=final,
    )


def _law(record: LawRecord, *asks: AskEvidence) -> LawEvidence:
    return LawEvidence(procedure_slug(record.procedure_id), record, NOW - timedelta(days=1), asks)


def _few_laws() -> list[LawEvidence]:
    done = FIRST + timedelta(days=300)
    return [
        _law(
            _record(1, completed_on=done),
            _ask("won", "full"),
            _ask("partly", "partial", kind="mep"),
            _ask("lost", "not_observed", kind=None),
            _ask("untraced", None),
            _ask("unknown", "unknown"),
            _ask("undated", "full", submitted=None),
            _ask("undated-amendment", "full", tabled=(None,)),
            _ask("late", "full", tabled=(done,)),
        ),
        _law(_record(2, completed_on=None), _ask("no-date", "full")),
        _law(_record(3, completed_on=done + timedelta(days=40), subjects=()), _ask("b", "full")),
        _law(
            _record(4, status="ongoing"),
            _ask("open", None),
            _ask("open-unknown", "unknown", submitted=None, tabled=()),
            _ask("decided", "full"),
        ),
        _law(_record(5, status="ongoing"), _ask("not-named", None)),
        _law(_record(6, status="withdrawn"), _ask("withdrawn", None)),
    ]


def test_with_few_laws_every_forecast_is_a_scenario_and_says_why() -> None:
    laws = _few_laws()
    targets = {law.slug for law in laws if law.law.procedure_id[-9:-5] in ("0001", "0004", "0006")}
    view = build_forecasts(laws, targets, generated_at=NOW, problems=("x: broken",))
    assert [item.ask_id for item in view.forecasts] == ["ask:open", "ask:open-unknown"]
    assert all(item.score is None and item.score_type == "scenario" for item in view.forecasts)
    plausible, unlikely = view.forecasts
    assert (plausible.scenario or "").startswith("Plausible")
    assert (unlikely.scenario or "").startswith("Unlikely")
    assert set(unlikely.missing_features) == {"ask_date"}
    check = view.validation
    assert (check.training_examples, check.training_wins, check.training_laws) == (4, 3, 2)
    assert not check.adequate
    assert any("4 decided asks from 2 completed law(s)" in r for r in check.reasons)
    assert all(reason in plausible.reasons for reason in check.reasons)
    rows = {law.procedure_id: law for law in view.laws}
    assert rows["2090/0001(COD)"].excluded == {
        "features not observed before the decision": 1,
        "features undated": 2,
        "final-act outcome unknown": 1,
        "no final-act outcome traced": 1,
    }
    assert rows["2090/0001(COD)"].note is not None
    assert rows["2090/0002(COD)"].excluded == {"completion date unknown": 1}
    assert rows["2090/0003(COD)"].training_examples == 1
    assert rows["2090/0004(COD)"].excluded == {"final-act outcome already decided": 1}
    assert (rows["2090/0004(COD)"].forecasts, rows["2090/0004(COD)"].note) == (2, None)
    assert rows["2090/0005(COD)"].excluded == {"open law not named as a target": 1}
    assert rows["2090/0006(COD)"].excluded == {"law withdrawn": 1}
    assert rows["2090/0006(COD)"].note == "Withdrawn: there is no later stage to forecast."
    assert not view.fallback_rule.computable
    assert "Skipped view x: broken." in view.limitations


def _signal_laws(count: int) -> list[LawEvidence]:
    """Organisations' asks win and Members' lose, in every law: the features carry signal."""
    laws: list[LawEvidence] = []
    for number in range(1, count + 1):
        done = FIRST + timedelta(days=30 * number)
        kinds: list[ActorKind] = ["organisation", "mep"]
        asks = [
            _ask(f"{number}-{i}", "not_observed" if i % 2 else "full", kind=kinds[i % 2])
            for i in range(10)
        ]
        laws.append(_law(_record(number, completed_on=done), *asks))
    laws.append(_law(_record(99, status="ongoing"), _ask("next", None)))
    return laws


def test_with_enough_validated_history_a_probability_is_published(
    capsys: pytest.CaptureFixture[str],
) -> None:
    laws = _signal_laws(40)
    view = build_forecasts(laws, {laws[-1].slug}, generated_at=NOW)
    assert view.validation.adequate, view.validation.reasons
    (only,) = view.forecasts
    assert only.score_type == "probability"
    assert (only.score or 0.0) > 0.9
    cli._print_forecast(view)  # pyright: ignore[reportPrivateUsage]
    printed = capsys.readouterr().out
    assert "Probabilities published: Brier" in printed
    assert "1 x probability" in printed


def test_an_open_ask_dated_after_the_cutoff_is_refused() -> None:
    late = NOW.date() + timedelta(days=1)
    laws = [_law(_record(1, status="ongoing"), _ask("future", None, submitted=late))]
    with pytest.raises(LeakageError):
        build_forecasts(laws, {laws[0].slug}, generated_at=NOW)


def test_laws_are_named_by_slug_number_celex_com_or_title() -> None:
    records = [_record(1), _record(2)]
    assert resolve_law("2090-0002-COD", records) is records[1]
    assert resolve_law("2090/2(COD)", records) is records[1]
    assert resolve_law("52092PC0001", records) is records[1]
    assert resolve_law("COM(2090) 1", records) is records[0]
    other = _record(3).model_copy(update={"title": "Gadget labelling directive"})
    assert resolve_law("gadget labelling", [*records, other]) is other
    with pytest.raises(ForecastError, match="more than one"):
        resolve_law("widgets fixture regulation", records)
    with pytest.raises(ForecastError, match="make atlas"):
        resolve_law("2090/0009(COD)", records)
    with pytest.raises(ForecastError, match="make atlas"):
        resolve_law("something unrelated entirely", records)
    with pytest.raises(ForecastError, match="empty"):
        resolve_law("   ", records)


def _fixture_view(laws: tuple[LawRecord, ...] | None = None) -> AtlasView:
    fixture = build_fixture()
    law = next(record for record in fixture.laws if record.procedure_id == LAW_A)
    return AtlasView(
        procedure_id=LAW_A,
        slug=procedure_slug(LAW_A),
        title=law.title,
        run_id="run-fixture",
        generated_at=NOW,
        ask_method="fixture",
        coverage=law.coverage,
        bundle=AtlasBundleView(
            laws=(law,) if laws is None else laws,
            documents=(),
            document_texts=(),
            passages=(),
            actors=fixture.actors,
            asks=tuple(ask for ask in fixture.asks if ask.procedure_id == LAW_A),
            amendments=fixture.amendments,
            articles=(),
            links=fixture.links,
            outcomes=fixture.outcomes,
        ),
        snapshot=fixture.graphs[0],
        rankings=(),
        limitations=(),
    )


def test_the_view_gives_each_ask_its_kind_dates_and_strongest_final_result() -> None:
    fixture = build_fixture()
    evidence = evidence_from_view(_fixture_view())
    assert evidence is not None
    asks = {ask.ask_id: ask for ask in evidence.asks}
    assert asks["ask:a-makers"].final == "full"
    assert asks["ask:a-makers"].actor_kind == "organisation"
    assert asks["ask:a-makers"].amendment_dates
    traced = {link.ask_id for link in fixture.links if link.status in ("published", "unconfirmed")}
    for ask_id, ask in asks.items():
        assert bool(ask.amendment_dates) == (ask_id in traced)
    assert evidence_from_view(_fixture_view(laws=())) is None


def test_the_command_reads_every_view_and_writes_the_forecast(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world = matching_world(tmp_path)
    bundle = world.collect().bundle
    law = pipeline.load_collected(bundle)
    pipeline.write_view(pipeline.build_view(law, generated_at=NOW - timedelta(days=1)), bundle)
    broken = world.root / "laws" / "2099-0001-COD"
    broken.mkdir(parents=True)
    (broken / pipeline.VIEW_FILE).write_text("{}", encoding="utf-8")
    orphan = world.root / "laws" / "2090-0001-COD"
    orphan.mkdir()
    (orphan / pipeline.VIEW_FILE).write_text(
        _fixture_view(laws=()).model_dump_json(by_alias=True), encoding="utf-8"
    )
    laws, problems = read_evidence(world.root)
    assert [item.slug for item in laws] == [bundle.name]
    assert len(problems) == 2

    code = cli.main(["forecast", bundle.name, "--data-root", str(world.root)])
    printed = capsys.readouterr().out
    assert code == 0, printed
    path = world.root / "laws" / FORECAST_FILE
    written = ForecastView.model_validate_json(path.read_bytes())
    assert written.laws[0].target
    assert written.fallback_rule.rule == "rapporteur_draft"
    assert set(json.loads(path.read_text(encoding="utf-8"))) >= {"forecasts", "validation"}
    assert "No probability published" in printed
    assert "Skipped view" in printed
    assert f"forecast: {path.absolute()}" in printed

    assert cli.main(["forecast", "2001/0001(COD)", "--data-root", str(world.root)]) == 1
    assert "make atlas" in capsys.readouterr().err


def test_writing_replaces_the_file_whole(tmp_path: Path) -> None:
    (tmp_path / "laws").mkdir()
    view = build_forecasts(_few_laws(), set(), generated_at=NOW)
    path = write_forecasts(view, tmp_path)
    assert ForecastView.model_validate_json(path.read_bytes()) == view
