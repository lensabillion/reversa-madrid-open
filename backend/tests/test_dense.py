"""The Qwen evaluation on LobbyPlag-shaped data, with a fake embedder and a fake judge."""

import hashlib
import runpy
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest
from demo_fixture import write_dataset
from practice_fixture import Records, practice_records

from influence.practice.dense import (
    DenseReport,
    cosine_scorer,
    funnel_table,
    judge_report,
    judge_scorer,
    main,
    measure_retrieval,
    measure_scorers,
    print_report,
    prose_dice_scores,
    render,
)
from influence.practice.folds import make_folds
from influence.practice.labels import PracticeDataError, PracticePair, build_practice_set
from influence.repositories.lobbyplag import DemoRepository, RawText
from influence.services.embedding import EmbeddingCache
from influence.services.qwen_onnx import QwenEmbedder

DIMENSIONS = 64


def embed(texts: Sequence[str]) -> list[list[float]]:
    """Hashed word counts: texts sharing words point the same way."""
    vectors: list[list[float]] = []
    for text in texts:
        vector = [0.0] * DIMENSIONS
        for word in text.casefold().split():
            vector[hashlib.sha256(word.encode()).digest()[0] % DIMENSIONS] += 1.0
        vectors.append(vector)
    return vectors


def judge(prompts: Sequence[str]) -> list[float]:
    """Log-odds that grow with the words the query and the document share."""
    scores: list[float] = []
    for prompt in prompts:
        query = prompt.split("<Query>: ")[1].split("\n<Document>: ")[0]
        document = prompt.split("<Document>: ")[1].split("<|im_end|>")[0]
        scores.append(float(len(set(query.split()) & set(document.split())) - 3))
    return scores


def _records() -> Records:
    """Six organizations, 36 verified copies and 36 rejected lookalikes, one deletion pair."""
    records = practice_records()
    next(a for a in records["amendments"] if a["uid"] == "a0-0")["text"] = [
        {"lang": "en", "old": "Article 0-0 requires consent.", "new": ""}
    ]
    next(p for p in records["proposals"] if p["uid"] == "p0-0")["text"] = {
        "old": "Article 0-0 requires consent.",
        "new": "",
    }
    return records


def _load(tmp_path: Path, records: Records) -> tuple[DemoRepository, DenseReport | None]:
    write_dataset(tmp_path, records)
    return DemoRepository.load(tmp_path), None


def test_retrieval_compares_bm25_dense_and_their_unions(tmp_path: Path) -> None:
    repository, _ = _load(tmp_path, _records())
    practice = build_practice_set(repository)
    rows, verified, passages = measure_retrieval(
        repository, practice, embed, model_id="fake", cache=None, batch_size=4
    )
    assert (verified, passages) == (36, 72)
    by_config = {row.config: row for row in rows}
    assert list(by_config) == [
        "bm25 delta",
        "bm25 whole text",
        "dense delta",
        "dense whole text",
        "bm25 delta + bm25 whole",
        "bm25 delta + bm25 whole + dense delta",
        "bm25 delta + bm25 whole + dense delta + dense whole",
        "dense delta + dense whole",
    ]
    for row in rows:
        assert row.pairs == 36
        assert all(0.0 <= value <= 1.0 for value in row.recall_at.values())
        assert (row.kind == "ranking") == (row.mrr is not None)
        assert (row.kind == "union") == (row.candidates_at is not None)
    # The deletion amendment has no new wording, so the whole-text queries cannot run for it.
    assert by_config["bm25 whole text"].query_errors == 1
    assert by_config["dense whole text"].query_errors == 1
    assert by_config["bm25 delta"].query_errors == 0
    # Copies repeat the amendment's edit, so every retriever finds almost all of them.
    assert by_config["bm25 delta"].recall_at["20"] > 0.9
    assert (
        by_config["bm25 delta + bm25 whole"].recall_at["20"]
        >= by_config["bm25 delta"].recall_at["20"]
    )


def test_an_unrunnable_query_is_a_miss_and_is_counted(tmp_path: Path) -> None:
    records = _records()
    next(a for a in records["amendments"] if a["uid"] == "a1-0")["text"] = [
        {"lang": "en", "old": "Article 1-0 requires consent.", "new": "word " * 900}
    ]
    repository, _ = _load(tmp_path, records)
    rows, _, _ = measure_retrieval(
        repository, build_practice_set(repository), embed, model_id="fake", cache=None
    )
    by_config = {row.config: row for row in rows}
    assert by_config["dense delta"].query_errors >= 1
    assert by_config["bm25 delta"].query_errors >= 1


def test_no_verified_pairs_is_an_error(tmp_path: Path) -> None:
    records = practice_records()
    for plag in records["plags"]:
        plag["verified"] = False
        plag["processing"] = {"checked": 1, "verified": 0}
    repository, _ = _load(tmp_path, records)
    with pytest.raises(PracticeDataError, match="No verified pairs"):
        measure_retrieval(
            repository, build_practice_set(repository), embed, model_id="fake", cache=None
        )


def test_scorers_use_the_harness_folds_and_include_the_judge_only_when_given(
    tmp_path: Path,
) -> None:
    repository, _ = _load(tmp_path, _records())
    practice = build_practice_set(repository)
    without, _ = measure_scorers(practice, embed, None, model_id="fake", cache=None)
    assert [row.scorer for row in without.rows] == [
        "lexical-delta-v1",
        "prose-dice",
        "qwen-cosine-delta",
        "qwen-cosine-whole",
    ]
    with_judge, plan = measure_scorers(practice, embed, judge, model_id="fake", cache=None)
    assert [row.scorer for row in with_judge.rows][-2:] == ["qwen-judge", "qwen-judge-changes"]
    assert len(plan.folds) == 5
    for name, scores in with_judge.scores.items():
        assert len(scores) == len(practice.pairs), name
        assert all(0.0 <= score <= 1.0 for score in scores), name
    for row in with_judge.rows:
        assert 0.0 <= row.auc_mean <= 1.0
        assert row.auc_p10 <= row.auc_mean + 1e-9


def _pair(name: str, old: str, new: str, proposal_old: str, proposal_new: str) -> PracticePair:
    return PracticePair(
        candidate_id=name,
        amendment_id=f"a-{name}",
        proposal_id=f"p-{name}",
        organization_id="org",
        amendment=RawText(old=old, new=new),
        submission=RawText(old=proposal_old, new=proposal_new),
    )


def test_a_proposal_with_no_text_and_an_amendment_too_long_to_read_score_zero() -> None:
    normal = _pair(
        "ok", "Keep logs.", "Keep logs for six months.", "x", "Keep logs for six months."
    )
    empty = _pair("empty", "Keep logs.", "Keep logs for six months.", "", "")
    long = _pair("long", "word " * 900, "other", "x", "other words here")
    test = [normal, empty, long]
    assert prose_dice_scores([], test)[1:] == [0.0, 0.0]
    assert prose_dice_scores([], test)[0] > 0.0
    delta = cosine_scorer(embed, model_id="fake", cache=None, batch_size=1, whole=False)([], test)
    whole = cosine_scorer(embed, model_id="fake", cache=None, batch_size=1, whole=True)([], test)
    assert delta[0] > 0.5
    assert delta[1:] == [0.0, 0.0]
    assert whole[0] > 0.5
    assert whole[1] == 0.0
    assert whole[2] > 0.0  # the whole new text is short even though the original is not
    for changes_only in (False, True):
        judged = judge_scorer(
            judge, model_id="fake", cache=None, batch_size=1, changes_only=changes_only
        )([], test)
        assert 0.0 < judged[0] < 1.0
        assert judged[1] == 0.0
        assert 0.0 < judged[2] < 1.0


def test_the_cache_makes_a_second_run_identical_and_free(tmp_path: Path) -> None:
    repository, _ = _load(tmp_path, _records())
    practice = build_practice_set(repository)
    cache = EmbeddingCache(tmp_path / "cache.sqlite3")
    calls: list[int] = []

    def counting(texts: Sequence[str]) -> list[list[float]]:
        calls.append(len(texts))
        return embed(texts)

    first, _ = measure_scorers(practice, counting, judge, model_id="fake", cache=cache)
    used = len(calls)
    second, _ = measure_scorers(practice, counting, judge, model_id="fake", cache=cache)
    assert len(calls) == used
    assert first.scores == second.scores


def test_the_funnel_reports_the_share_each_cosine_cut_keeps() -> None:
    scores = [0.9, 0.85, 0.75, 0.65, 0.55, 0.45]
    labels = [True, True, True, False, False, False]
    rows = {row.cosine_at_least: row for row in funnel_table(scores, labels)}
    assert (rows[0.5].positives_kept, rows[0.5].negatives_kept) == (1.0, 0.666667)
    assert (rows[0.7].positives_kept, rows[0.7].negatives_kept) == (1.0, 0.0)
    assert rows[0.8].positives_kept == pytest.approx(0.666667)
    assert rows[0.8].pairs_kept == pytest.approx(0.333333)


def test_an_amendment_with_two_verified_proposals_is_searched_once_and_counted_twice(
    tmp_path: Path,
) -> None:
    records = _records()
    records["plags"].append(
        {
            "uid": "c-extra",
            "amendment": "a0-2",
            "proposal": "p1-0",
            "verified": True,
            "match": 0.9,
            "processing": {"checked": 0, "verified": 0},
        }
    )
    repository, _ = _load(tmp_path, records)
    rows, verified, _ = measure_retrieval(
        repository, build_practice_set(repository), embed, model_id="fake", cache=None
    )
    assert verified == 37
    assert {row.pairs for row in rows} == {37}


def test_a_judge_that_separates_the_classes_gets_thresholds_that_hold_out(
    tmp_path: Path,
) -> None:
    # Wilson needs about 35 correct in the development folds to clear the 0.90 floor, so the
    # invented world must be larger than the default.
    repository, _ = _load(tmp_path, practice_records(organizations=14))
    practice = build_practice_set(repository)
    plan = make_folds(practice.pairs, 5)
    perfect = [0.95 if item.influenced else 0.05 for item in practice.pairs]
    report = judge_report(
        "perfect", perfect, practice, plan, {"model.onnx": "0" * 64}, changes_only=False
    )
    assert report.scorer == "perfect"
    assert report.separation.positives_mean > 0.9 > 0.1 > report.separation.negatives_mean
    assert report.development_folds == (0, 2, 4)
    assert report.held_out_folds == (1, 3)
    assert report.reranker_sha256 == {"model.onnx": "0" * 64}
    copied, reworded = report.proposals
    assert (copied.tier, reworded.tier) == ("copied", "reworded")
    assert copied.threshold is not None
    assert copied.held_out is not None
    assert copied.held_out.positives == copied.held_out.pairs
    # The reworded tier is read on its own band, below the copied cut.
    assert (copied.below, reworded.below) == (None, copied.threshold)
    assert report.clipped_prompts == 0
    assert len(report.table) == 9


def test_a_judge_that_cannot_separate_the_classes_gets_no_threshold(tmp_path: Path) -> None:
    repository, _ = _load(tmp_path, _records())
    practice = build_practice_set(repository)
    plan = make_folds(practice.pairs, 5)
    report = judge_report(
        "flat", [0.5] * len(practice.pairs), practice, plan, {}, changes_only=True
    )
    assert all(found.threshold is None for found in report.proposals)
    assert all(found.development is None and found.held_out is None for found in report.proposals)
    assert report.separation.positives_mean == report.separation.negatives_mean == 0.5


def test_the_judge_report_counts_the_prompts_it_saw_cut(tmp_path: Path) -> None:
    records = _records()
    long = "Article 0-1 requires consent " + "and much more " * 120
    next(p for p in records["proposals"] if p["uid"] == "p0-1")["text"] = {
        "old": "Article 0-1 requires consent.",
        "new": long,
    }
    repository, _ = _load(tmp_path, records)
    practice = build_practice_set(repository)
    plan = make_folds(practice.pairs, 5)
    flat = [0.5] * len(practice.pairs)
    cut = sum(item.pair.proposal_id == "p0-1" for item in practice.pairs)
    assert cut > 0
    for changes_only in (False, True):
        report = judge_report("flat", flat, practice, plan, {}, changes_only=changes_only)
        assert report.clipped_prompts == cut


class _CountingEmbedder(QwenEmbedder):
    """The fake embedder, seen by the command as a Qwen embedder that cut three texts."""

    def __init__(self) -> None:  # pyright: ignore[reportMissingSuperCall]
        self.truncated = 3

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        return embed(texts)


def test_the_command_prints_how_many_texts_the_embedder_cut(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_dataset(tmp_path, _records())
    out = tmp_path / "dense.json"
    argv = ["--data", str(tmp_path), "--model", str(tmp_path / "model"), "--out", str(out)]
    assert main(argv, load=lambda directory: _CountingEmbedder()) == 0
    assert "The embedder cut 3 texts at 512 tokens" in capsys.readouterr().out


def _run(data: Path, out: Path, *extra: str) -> int:
    return main(
        ["--data", str(data), "--model", str(data / "model"), "--out", str(out), *extra],
        load=lambda directory: embed,
        load_judge=lambda directory: judge,
    )


def test_the_command_writes_deterministic_json_and_prints_every_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_dataset(tmp_path, _records())
    model = tmp_path / "model"
    (model / "onnx").mkdir(parents=True)
    (model / "onnx" / "model_int8.onnx").write_bytes(b"weights")
    reranker = tmp_path / "reranker"
    reranker.mkdir()
    (reranker / "model.onnx").write_bytes(b"judge weights")
    out = tmp_path / "dense.json"
    options = ("--reranker", str(reranker), "--cache", str(tmp_path / "cache.sqlite3"))
    assert _run(tmp_path, out, *options) == 0
    first = out.read_text(encoding="utf-8")
    report = DenseReport.model_validate_json(first)
    assert first == render(report)
    assert report.kind == "dense-meaning-v2"
    assert set(report.input_sha256) == {
        "amendments.json",
        "proposals.json",
        "plags.json",
        "documents.json",
        "lobbyists.json",
    }
    assert set(report.model_sha256) == {"onnx/model_int8.onnx"}
    assert [judge.scorer for judge in report.judges] == ["qwen-judge", "qwen-judge-changes"]
    assert set(report.judges[0].reranker_sha256) == {"model.onnx"}
    printed = capsys.readouterr().out
    for expected in ("36 verified pairs", "funnel", "qwen-judge-changes P(yes)", "Wrote"):
        assert expected in printed
    assert _run(tmp_path, out, *options) == 0
    assert out.read_text(encoding="utf-8") == first


def test_the_command_without_a_reranker_reports_no_judges(tmp_path: Path) -> None:
    write_dataset(tmp_path, _records())
    out = tmp_path / "dense.json"
    assert _run(tmp_path, out) == 0
    report = DenseReport.model_validate_json(out.read_text(encoding="utf-8"))
    assert report.judges == ()
    assert report.model_sha256 == {}
    assert [row.scorer for row in report.scorers][-1] == "qwen-cosine-whole"


def test_printing_names_a_threshold_or_says_none_reaches_the_floor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository, _ = _load(tmp_path, _records())
    practice = build_practice_set(repository)
    plan = make_folds(practice.pairs, 5)
    good = judge_report(
        "perfect",
        [0.95 if item.influenced else 0.05 for item in practice.pairs],
        practice,
        plan,
        {},
        changes_only=False,
    )
    flat = judge_report("flat", [0.5] * len(practice.pairs), practice, plan, {}, changes_only=False)
    rows, verified, passages = measure_retrieval(
        repository, practice, embed, model_id="fake", cache=None
    )
    measured, _ = measure_scorers(practice, embed, None, model_id="fake", cache=None)
    report = DenseReport(
        kind="dense-meaning-v2",
        model_id="fake",
        input_sha256={},
        model_sha256={},
        verified_pairs=verified,
        labelled_pairs=len(practice.pairs),
        corpus_passages=passages,
        retrieval=rows,
        scorers=measured.rows,
        funnel=funnel_table(
            measured.scores["qwen-cosine-delta"], [i.influenced for i in practice.pairs]
        ),
        judges=(good, flat),
        caveats=(),
    )
    print_report(report, "timings line")
    printed = capsys.readouterr().out
    assert "held-out" in printed
    assert "no threshold reaches the floor" in printed
    assert printed.rstrip().endswith("timings line")


def test_the_command_fails_cleanly_on_unusable_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "dense.json"
    assert _run(tmp_path / "missing", out) == 1
    assert not out.exists()
    assert "error:" in capsys.readouterr().err


def test_the_command_rejects_a_missing_output_directory(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _run(tmp_path, tmp_path / "absent" / "dense.json")
    assert exit_info.value.code == 2


def test_the_module_runs_as_a_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from influence.services.qwen_onnx import QwenError

    write_dataset(tmp_path, _records())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "influence.practice.dense",
            "--data",
            str(tmp_path),
            "--model",
            str(tmp_path / "no-such-model"),
            "--out",
            str(tmp_path / "dense.json"),
        ],
    )
    monkeypatch.delitem(sys.modules, "influence.practice.dense", raising=False)
    # Run as a script the real loader is used; with no model files it reports that cleanly.
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("influence.practice.dense", run_name="__main__")
    assert exit_info.value.code == 1
    assert QwenError is not None
