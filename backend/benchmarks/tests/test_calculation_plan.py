"""Full-signal ablations retain each feature's meaning and validate offline Jev provenance."""

import sys
from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks import calculation_plan as benchmark
from benchmarks.jev_gate3 import PreparedTrial, digest, write
from benchmarks.tests.test_jev_practice import pair, save_cache, trial
from influence.practice.folds import FoldPlan
from influence.practice.labels import IdenticalInputs, PracticeSet
from influence.services.signals import SignalCorpus


@pytest.mark.parametrize("semantic", [False, True])
@pytest.mark.parametrize("judge", [False, True])
def test_jev_variants_preserve_every_previous_ablation(semantic: bool, judge: bool) -> None:
    original = benchmark.feature_variants(semantic=semantic, judge=judge, jev=False)
    expanded = benchmark.feature_variants(semantic=semantic, judge=judge, jev=True)
    assert {name: expanded[name] for name in original} == original
    assert expanded["deterministic_context_jev"] == (
        *benchmark.DETERMINISTIC,
        *benchmark.CONTEXT,
        *benchmark.JEV,
    )
    assert "all_signals_jev" in expanded if semantic else "all_signals_jev" not in expanded
    if semantic:
        expected = original["all_signals_judge" if judge else "all_signals"]
        assert expanded["all_signals_jev"] == (*expected, *benchmark.JEV)
    if judge:
        assert expanded["deterministic_context_judge_jev"] == (
            *original["deterministic_context_judge"],
            *benchmark.JEV,
        )
    assert set(benchmark.JEV).isdisjoint(benchmark.JUDGE)
    assert all(len(names) == len(set(names)) for names in expanded.values())


def prepared_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, PracticeSet]:
    value = trial()
    labelled = pair(0, True)
    labelled = replace(labelled, pair=replace(labelled.pair, candidate_id="deletion"))
    practice = PracticeSet(
        pairs=(labelled,),
        outcomes={},
        excluded={},
        identical_inputs=IdenticalInputs(groups=0, pairs=0, conflicting_groups=0),
    )
    plan = FoldPlan(grouping="organizations_with_purge", components=(), folds=())

    def prepare(data: Path) -> tuple[PreparedTrial, PracticeSet, FoldPlan]:
        return value, practice, plan

    monkeypatch.setattr(benchmark, "prepared", prepare)
    inputs = tmp_path / "inputs.json"
    write(inputs, value)
    save_cache(tmp_path, value)
    return inputs, practice


def test_cached_features_have_explicit_names_and_complete_provenance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inputs, practice = prepared_fixture(monkeypatch, tmp_path)
    pairs = [item.pair for item in practice.pairs]
    features, provenance = benchmark.jev_features(tmp_path, inputs, tmp_path, pairs)
    assert features == {"deletion": dict.fromkeys(benchmark.JEV, 0.8)}
    assert provenance["model"] == "jev-1.13.0"
    assert provenance["inputs_sha256"] == digest(inputs)
    assert provenance["ledger_sha256"] == digest(tmp_path / "ledger.json")
    assert provenance["request_sha256_by_candidate"]
    assert provenance["response_sha256_by_request"]
    merged = benchmark.signal_rows(pairs, SignalCorpus(["logs"]), features)[0]
    assert all(merged[name] == 0.8 for name in benchmark.JEV)
    assert "entailment_score" not in merged
    assert set(benchmark.DETERMINISTIC + benchmark.CONTEXT) <= merged.keys()


@pytest.mark.parametrize("mutation", ["source", "state", "pair", "incomplete", "response"])
def test_wrong_preparation_and_incomplete_or_tampered_cache_cannot_enter_fits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mutation: str
) -> None:
    inputs, practice = prepared_fixture(monkeypatch, tmp_path)
    value = trial()
    pairs = [item.pair for item in practice.pairs]
    if mutation == "source":
        write(inputs, value.model_copy(update={"source_hashes": {"changed.json": "bad"}}))
    elif mutation == "state":
        changed = value.cases[0].model_copy(
            update={"state": {**value.cases[0].state, "submission_new": "Different request"}}
        )
        write(inputs, value.model_copy(update={"cases": [changed]}))
    elif mutation == "pair":
        pairs = [replace(pairs[0], candidate_id="wrong")]
    elif mutation == "incomplete":
        (tmp_path / "ledger.json").unlink()
    else:
        next((tmp_path / "results").glob("*.json")).write_text("{}")
    with pytest.raises(ValueError, match=r"inputs differ|Missing complete|hash mismatch"):
        benchmark.jev_features(tmp_path, inputs, tmp_path, pairs)


@pytest.mark.parametrize("flag", ["--jev-inputs", "--jev-cache"])
def test_partial_jev_cli_configuration_is_refused_before_loading_data(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["calculation_plan", "--data", "absent", "--out", "unused", flag, "absent"]
    )
    with pytest.raises(SystemExit) as error:
        benchmark.main()
    assert error.value.code == 2
    assert "must be supplied together" in capsys.readouterr().err
