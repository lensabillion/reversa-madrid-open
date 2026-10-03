"""Part 8 · The batch over many laws: selection, resume, failures recorded, the banner.

The laws are collect's tiny scripted world (`test_collect.make_world`): the AI Act, a
completed law with amendments and consultation feedback, and Toy Safety, an ongoing law
with one committee amendment. No test reaches the network.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from test_cellar import sparql
from test_collect import AI_ACT, NOW, ONGOING, ai_act_script, make_world, scripted_cli
from test_parltrack import committee_record, write_dump

from influence import cli
from influence.extraction.layout import procedure_slug
from influence.schemas.batch import BatchRun, BatchSelection
from influence.services import batch, lineage_assembly, pipeline
from influence.services.collect import CollectInputs, CollectSettings, load_catalog
from influence.services.pipeline import PipelineError

DATA_ACT = "2022/0047(COD)"
SCRIPT = [
    *ai_act_script(),
    ("procedure/2024_100>", sparql()),
    ("procedure/2022_47>", sparql()),
]


def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scripted_cli(monkeypatch, make_world(tmp_path, SCRIPT))


def read_batch(root: Path) -> BatchRun:
    return BatchRun.model_validate_json((root / "laws" / batch.BATCH_FILE).read_bytes())


def bundle(root: Path, procedure: str) -> Path:
    return root / "laws" / procedure_slug(procedure)


def statuses(run: BatchRun, procedure: str) -> dict[str, str]:
    (law,) = (law for law in run.laws if law.procedure_id == procedure)
    return {step.step: step.status for step in law.steps}


def run_cli(root: Path, *args: str) -> int:
    return cli.main(["batch", *args, "--data-root", str(root)])


# --- Named laws -----------------------------------------------------------------------------


def test_two_named_laws_run_every_default_step_and_write_the_banner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world(tmp_path, monkeypatch)

    # "AI Act" and its procedure number name one law, which runs once.
    status = run_cli(tmp_path, "--laws", f"AI Act,{ONGOING},{AI_ACT}")

    output = capsys.readouterr().out
    assert status == 0
    run = read_batch(tmp_path)
    assert [law.procedure_id for law in run.laws] == [AI_ACT, ONGOING]
    assert [law.query for law in run.laws] == ["AI Act", ONGOING]
    assert run.selection == BatchSelection(mode="laws", laws=("AI Act", ONGOING, AI_ACT))
    assert run.steps == batch.DEFAULT_STEPS
    assert (run.attachments, run.refresh) == (False, False)
    for law in run.laws:
        assert law.status == "complete"
        assert law.run_id is not None
        assert [(s.step, s.status) for s in law.steps] == [
            ("collect", "done"),
            *((step, "done") for step in batch.DEFAULT_STEPS),
        ]
        for step in batch.DEFAULT_STEPS:
            written = bundle(tmp_path, law.procedure_id or "") / batch.OUTPUTS[step]
            assert batch.built_from(written) == law.run_id
        assert not (bundle(tmp_path, law.procedure_id or "") / "atlas.json").exists()
    ai_act, ongoing = run.laws
    assert (ai_act.amendments, ongoing.amendments) == (2, 1)
    assert ai_act.title == "Artificial Intelligence Act"
    assert {row.layer: row.status for row in ai_act.coverage}["asks"] == "partial"
    banner = run.banner
    assert (banner.laws_selected, banner.laws_attempted, banner.laws_complete) == (2, 2, 2)
    assert (banner.laws_partial, banner.laws_failed, banner.amendments_covered) == (0, 0, 3)
    assert banner.layers_missing["meetings"] == 2
    assert banner.steps_failed == {}
    assert banner.finished_at is not None
    assert banner.finished_at >= banner.started_at
    assert "Batch of 2 laws; steps: collect, coordinated, channels, lineage, directions" in output
    assert f"[1/2] {AI_ACT} complete in " in output
    assert "collect done" in output
    assert "; 2 amendments" in output
    assert f"[2/2] {ONGOING} complete in " in output
    assert "Batch: 2 of 2 laws attempted, 2 complete, 0 partial, 0 failed; 3 amendments" in output
    assert "  steps failed (laws): none" in output
    assert f"batch: {tmp_path / 'laws' / 'batch.json'}" in output


def test_a_rerun_reuses_the_collect_run_and_skips_every_built_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world(tmp_path, monkeypatch)
    assert run_cli(tmp_path, "--laws", f"{AI_ACT},{ONGOING}") == 0
    first = read_batch(tmp_path)
    (bundle(tmp_path, AI_ACT) / batch.OUTPUTS["lineage"]).unlink()
    capsys.readouterr()

    assert run_cli(tmp_path, "--laws", f"{AI_ACT},{ONGOING}") == 0

    run = read_batch(tmp_path)
    assert [law.run_id for law in run.laws] == [law.run_id for law in first.laws]
    assert statuses(run, AI_ACT) == {
        "collect": "reused",
        "coordinated": "skipped",
        "channels": "skipped",
        "lineage": "done",
        "directions": "skipped",
    }
    assert set(statuses(run, ONGOING).values()) == {"reused", "skipped"}
    assert "collect reused, coordinated skipped" in capsys.readouterr().out


def test_refresh_collects_again_and_redoes_every_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world(tmp_path, monkeypatch)
    assert run_cli(tmp_path, "--laws", AI_ACT) == 0

    assert run_cli(tmp_path, "--laws", AI_ACT, "--refresh") == 0

    run = read_batch(tmp_path)
    assert run.refresh
    assert set(statuses(run, AI_ACT).values()) == {"done"}


def test_a_failing_law_is_recorded_and_the_batch_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world(tmp_path, monkeypatch)

    # An unknown name, then a law with nothing to analyse, then one that works.
    status = run_cli(tmp_path, "--laws", f"No such regulation anywhere,{DATA_ACT},{AI_ACT}")

    captured = capsys.readouterr()
    assert status == 1
    run = read_batch(tmp_path)
    unknown, data_act, ai_act = run.laws
    assert (unknown.procedure_id, unknown.status, unknown.steps) == (None, "failed", ())
    assert unknown.error is not None
    assert unknown.error.startswith("CollectError: No procedure title in the catalog matches")
    assert (data_act.procedure_id, data_act.status, data_act.run_id) == (DATA_ACT, "failed", None)
    assert data_act.error is not None
    assert "no amendments and no consultation submissions" in data_act.error
    assert ai_act.status == "complete"
    assert (run.banner.laws_failed, run.banner.laws_complete) == (2, 1)
    assert "[1/3] No such regulation anywhere failed" in captured.out
    assert "  CollectError: No procedure title" in captured.err


def test_a_failing_step_leaves_the_law_partial_and_the_other_steps_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world(tmp_path, monkeypatch)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise PipelineError("lineage broke")

    monkeypatch.setattr(lineage_assembly, "build_lineage", broken)

    assert run_cli(tmp_path, "--laws", f"{AI_ACT},{ONGOING}") == 1

    run = read_batch(tmp_path)
    assert [law.status for law in run.laws] == ["partial", "partial"]
    assert statuses(run, AI_ACT)["lineage"] == "failed"
    assert statuses(run, AI_ACT)["directions"] == "done"
    (failed,) = (step for step in run.laws[0].steps if step.status == "failed")
    assert failed.error == "PipelineError: lineage broke"
    assert run.banner.steps_failed == {"lineage": 2}
    captured = capsys.readouterr()
    assert "lineage failed" in captured.out
    assert "  lineage: PipelineError: lineage broke" in captured.err
    assert "  steps failed (laws): lineage 2" in captured.out


def test_an_unreadable_collect_run_fails_the_law_before_any_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world(tmp_path, monkeypatch)
    manifest = bundle(tmp_path, AI_ACT) / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")

    assert run_cli(tmp_path, "--laws", AI_ACT) == 1

    (law,) = read_batch(tmp_path).laws
    assert (law.status, law.steps) == ("failed", ())
    assert law.error is not None
    assert law.error.startswith("RecordError: The manifest in")


# --- The atlas step -------------------------------------------------------------------------


def test_the_atlas_step_writes_the_view_and_its_clusters_before_directions_read_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world(tmp_path, monkeypatch)

    assert run_cli(tmp_path, "--laws", AI_ACT, "--steps", "directions,atlas") == 0

    run = read_batch(tmp_path)
    assert run.steps == ("atlas", "directions")
    law = bundle(tmp_path, AI_ACT)
    (row,) = run.laws
    assert batch.built_from(law / "atlas.json") == row.run_id
    assert batch.built_from(law / "coordinated.json") == row.run_id
    directions = json.loads((law / "directions.json").read_bytes())
    assert directions["atlas_run_id"] == row.run_id


def test_a_failed_atlas_step_removes_the_view_of_an_earlier_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world(tmp_path, monkeypatch)
    assert run_cli(tmp_path, "--laws", AI_ACT, "--steps", "atlas") == 0

    def broken(*_args: object, **_kwargs: object) -> None:
        raise PipelineError("view broke")

    monkeypatch.setattr(pipeline, "build_view", broken)

    assert run_cli(tmp_path, "--laws", AI_ACT, "--steps", "atlas", "--refresh") == 1

    assert statuses(read_batch(tmp_path), AI_ACT)["atlas"] == "failed"
    assert not (bundle(tmp_path, AI_ACT) / "atlas.json").exists()


# --- Every procedure amended since a date ---------------------------------------------------


def test_since_selects_the_catalogs_procedures_amended_since_most_amended_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world(tmp_path, monkeypatch)

    status = run_cli(tmp_path, "--since", "2019", "--with-amendments")

    assert status == 0
    run = read_batch(tmp_path)
    # Two procedures amended since 2019 are not in the dossiers catalog and are left out.
    assert [law.procedure_id for law in run.laws] == [AI_ACT, ONGOING]
    assert run.selection == BatchSelection(mode="since", since=date(2019, 1, 1))
    assert "Scanning the amendment dumps for amendments tabled since 2019-01-01" in (
        capsys.readouterr().out
    )


def test_since_with_a_limit_keeps_the_most_amended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world(tmp_path, monkeypatch)

    assert run_cli(tmp_path, "--since", "2019", "--with-amendments", "--limit", "1") == 0

    run = read_batch(tmp_path)
    assert [law.procedure_id for law in run.laws] == [AI_ACT]
    assert run.banner.laws_selected == 1


def test_amended_since_counts_dated_records_on_or_after_the_day(tmp_path: Path) -> None:
    dump = write_dump(
        tmp_path / "ep_amendments.json.zst",
        [
            committee_record(id="a", date="2019-01-01T00:00:00"),
            committee_record(id="b", date="2018-12-31T00:00:00"),
            committee_record(id="c", reference=ONGOING, date="2024-05-02"),
            committee_record(id="d", reference=ONGOING, date=None),
            committee_record(id="e", reference=None),
        ],
    )

    counts = batch.amended_since([dump, dump], date(2019, 1, 1))

    assert counts == {AI_ACT: 2, ONGOING: 2}


def test_plan_since_orders_by_amendments_then_procedure_and_drops_unknowns(
    tmp_path: Path,
) -> None:
    make_world(tmp_path)
    inputs = CollectInputs.under(tmp_path)
    catalog = load_catalog(inputs.dossiers, tmp_path / "catalog")
    counts = batch.amended_since(
        (inputs.committee_amendments, inputs.plenary_amendments), date(2019, 1, 1)
    )
    counts[ONGOING] = counts[AI_ACT]

    planned = batch.plan_since(catalog, counts, None)

    assert [law.procedure_id for law in planned] == [AI_ACT, ONGOING]
    assert planned[0].title == "Artificial Intelligence Act"
    assert batch.plan_since(catalog, counts, 1) == planned[:1]


# --- Inputs, outputs and usage --------------------------------------------------------------


def test_an_empty_plan_still_writes_a_finished_batch(tmp_path: Path) -> None:
    world_ = make_world(tmp_path)
    settings = batch.BatchSettings(
        collect=CollectSettings(data_root=tmp_path, code_revision="src-test", hardware=None),
        steps=batch.DEFAULT_STEPS,
        selection=BatchSelection(mode="laws"),
    )

    run, path = batch.run_batch(
        (), inputs=world_.inputs, settings=settings, fetcher=world_.fetcher, clock=lambda: NOW
    )

    assert path == tmp_path / "laws" / "batch.json"
    assert read_batch(tmp_path) == run
    assert run.laws == ()
    assert run.banner.finished_at == datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    assert run.banner.hardware  # the machine's own platform string


def test_a_step_output_is_trusted_only_when_it_names_its_run(tmp_path: Path) -> None:
    path = tmp_path / "view.json"
    assert batch.built_from(path) is None
    for content, expected in (
        ("not json", None),
        ("[1]", None),
        ('{"run_id": 3}', None),
        ('{"run_id": "20261003T120000Z"}', "20261003T120000Z"),
    ):
        path.write_text(content, encoding="utf-8")
        assert batch.built_from(path) == expected


def test_missing_inputs_stop_the_batch_before_any_law(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_cli(tmp_path, "--laws", AI_ACT) == 1

    assert "required input files are missing" in capsys.readouterr().err
    assert not (tmp_path / "laws" / "batch.json").exists()


def test_an_unreadable_amendment_dump_stops_the_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world(tmp_path, monkeypatch)
    CollectInputs.under(tmp_path).committee_amendments.write_bytes(b"not zstd")

    assert run_cli(tmp_path, "--since", "2019", "--with-amendments") == 1

    error = capsys.readouterr().err
    assert "unreadable Parltrack dump" in error
    assert "No law was run." in error


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--since", "2019"], "--since and --with-amendments go together"),
        (["--laws", AI_ACT, "--with-amendments"], "--since and --with-amendments go together"),
        (["--laws", AI_ACT, "--limit", "2"], "--limit applies to --since only"),
        (["--laws", " , "], "name at least one law"),
        (["--since", "twenty"], "not a year: 'twenty'"),
        (["--laws", AI_ACT, "--steps", "atlas,report"], "unknown 'report'"),
        ([], "one of the arguments --laws --since is required"),
    ],
)
def test_usage_errors_exit_with_status_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], args: list[str], message: str
) -> None:
    with pytest.raises(SystemExit) as stopped:
        run_cli(tmp_path, *args)

    assert stopped.value.code == 2
    assert message in capsys.readouterr().err
