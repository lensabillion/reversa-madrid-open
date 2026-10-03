"""Lineage review: a reproducible selection, a human-readable export, and an honest gate."""

import csv
import io
import json
import runpy
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from influence.practice.lineage_review import (
    LabelRecord,
    ReviewRow,
    ReviewSummary,
    claim_id,
    export_rows,
    main,
    meets_gate,
    read_labels,
    read_rows,
    review_rows,
    summarise,
    to_csv,
    to_markdown,
)
from influence.schemas.atlas import SourceSpan
from influence.schemas.lineage import (
    AdoptedPhrase,
    AmendmentAdoption,
    LineageCounts,
    LineageView,
    MatchKind,
    OriginMatch,
)
from influence.services.audit import AuditError, wilson_interval

SPAN = SourceSpan(
    record_id="art:32099R0001:article-6-1", start=0, end=20, text="Providers shall keep"
)


def _phrase(
    key: str, words: int, kind: MatchKind = "verbatim", similarity: float | None = None
) -> AdoptedPhrase:
    text = " ".join(f"{key}{i}" for i in range(words))
    return AdoptedPhrase(
        phrase_id=f"phrase:{key * 16}"[:23],
        kind=kind,
        text=text,
        words=words,
        final_spans=(SPAN,),
        similarity=similarity,
    )


def _adoption(
    number: int,
    phrase: AdoptedPhrase,
    *,
    stage: str = "committee",
    authors: tuple[tuple[str, str], ...] = (("actor:mep:1", "Ada Example"),),
    kind: MatchKind = "verbatim",
) -> AmendmentAdoption:
    return AmendmentAdoption.model_validate(
        {
            "amendment_id": f"am:2099-0001-COD:IMCO:{number}",
            "kind": kind,
            "stage": stage,
            "author_ids": [author for author, _ in authors],
            "author_names": [name for _, name in authors],
            "tabled_on": date(2099, 3, 1),
            "phrase_ids": [phrase.phrase_id],
            "adopted_words": phrase.words,
            "inserted_words": phrase.words + 10,
            "longest_run": phrase.words,
        }
    )


def _origin(
    phrase: AdoptedPhrase,
    amendment_numbers: tuple[int, ...],
    *,
    organisation: str | None = "Acme",
    published: datetime | None = datetime(2099, 1, 5, tzinfo=UTC),
    precedes: bool | None = True,
    is_citation: bool = False,
    document: str = "doc:hys_attachment:1",
) -> OriginMatch:
    return OriginMatch(
        phrase_id=phrase.phrase_id,
        document_id=document,
        organisation=organisation,
        published_at=published,
        span=SourceSpan(record_id=document, start=0, end=13, text="Providers say"),
        words=phrase.words,
        amendment_ids=tuple(f"am:2099-0001-COD:IMCO:{n}" for n in amendment_numbers),
        precedes=precedes,
        is_citation=is_citation,
    )


P_BIG = _phrase("a", 20)
P_MID = _phrase("b", 14)
P_SHARED = _phrase("c", 12)
P_SEM = _phrase("d", 6, "semantic", 0.9)
MEP_1, MEP_2, MEP_3 = (
    ("actor:mep:1", "Ada Example"),
    ("actor:mep:2", "Bo Sample"),
    ("actor:mep:3", "Cy"),
)


def view(
    extra: tuple[AmendmentAdoption, ...] = (), phrases: tuple[AdoptedPhrase, ...] = ()
) -> LineageView:
    adoptions = (
        _adoption(1, P_BIG, authors=(MEP_1,)),
        _adoption(2, P_MID, stage="plenary", authors=()),
        _adoption(3, P_SHARED, authors=(MEP_2,)),
        _adoption(4, P_SHARED, authors=(MEP_3,)),
        _adoption(5, P_SEM, authors=(MEP_1,), kind="semantic"),
        *extra,
    )
    return LineageView(
        procedure_id="2099/0001(COD)",
        slug="2099-0001-COD",
        title="Widget Act",
        run_id="run-1",
        generated_at=datetime(2099, 12, 1, tzinfo=UTC),
        method="adopted-phrases",
        method_revision="lineage-1.0",
        counts=LineageCounts(
            amendments=10,
            amendments_adopting=len(adoptions),
            adopted_phrases=4 + len(phrases),
            documents_read=3,
            documents_with_origin=2,
        ),
        adopted_phrases=(P_BIG, P_MID, P_SHARED, P_SEM, *phrases),
        adoptions=adoptions,
        origins=(
            _origin(P_BIG, (1,), precedes=None, published=None, document="doc:hys_attachment:9"),
            _origin(
                P_BIG, (1,), organisation=None, is_citation=True, document="doc:hys_attachment:2"
            ),
            _origin(P_BIG, (1,), organisation="Acme", document="doc:hys_attachment:1"),
            _origin(P_SHARED, (3, 4)),
        ),
    )


GROUPS = {"actor:mep:1": "PPE", "actor:mep:2": "S&D"}


def test_the_strongest_claims_come_first_then_a_seeded_sample() -> None:
    rows = review_rows(view(), 4, seed=3)
    assert [row.selection for row in rows] == ["strongest", "strongest", "sample", "sample"]
    assert [row.phrase_words for row in rows[:2]] == [20, 14]
    assert len({row.claim_id for row in rows}) == 4
    assert rows[0].claim_id == claim_id("am:2099-0001-COD:IMCO:1", P_BIG.phrase_id)
    assert rows == review_rows(view(), 4, seed=3)


def test_semantic_claims_rank_after_verbatim_and_carry_their_similarity() -> None:
    rows = review_rows(view(), 5)
    assert rows[-1].kind == "semantic" or any(row.kind == "semantic" for row in rows)
    semantic = next(row for row in rows if row.kind == "semantic")
    assert semantic.similarity == pytest.approx(0.9)


def test_wording_in_several_amendments_is_marked_as_coalition_wording() -> None:
    rows = {row.amendment_id: row for row in review_rows(view(), 5)}
    shared = rows["am:2099-0001-COD:IMCO:3"]
    assert (shared.shared_by_amendments, shared.coalition) == (2, True)
    assert rows["am:2099-0001-COD:IMCO:1"].coalition is False


def test_origins_are_attached_to_their_amendment_and_dated_ones_that_precede_come_first() -> None:
    rows = {row.amendment_id: row for row in review_rows(view(), 5)}
    first = rows["am:2099-0001-COD:IMCO:1"]
    assert [origin.document_id for origin in first.origins] == [
        "doc:hys_attachment:1",
        "doc:hys_attachment:2",
        "doc:hys_attachment:9",
    ]
    assert first.origins[1].is_citation
    assert first.origins[2].precedes is None
    assert rows["am:2099-0001-COD:IMCO:2"].origins == ()
    assert len(rows["am:2099-0001-COD:IMCO:4"].origins) == 1


def test_groups_come_from_the_map_and_committee_text_has_none() -> None:
    rows = {row.amendment_id: row for row in review_rows(view(), 5, groups=GROUPS)}
    assert rows["am:2099-0001-COD:IMCO:1"].groups == ("PPE",)
    assert rows["am:2099-0001-COD:IMCO:2"].groups == ("committee_text",)
    assert rows["am:2099-0001-COD:IMCO:4"].groups == ("unknown",)
    assert rows["am:2099-0001-COD:IMCO:1"].final_provision == SPAN.record_id


def test_a_review_asks_for_at_least_one_claim_and_never_pads() -> None:
    with pytest.raises(AuditError, match="at least one"):
        review_rows(view(), 0)
    assert len(review_rows(view(), 50)) == 5


def test_the_sample_is_spread_over_stages_kinds_and_groups_not_filled_by_one_of_them() -> None:
    big = [_phrase("e", 30), _phrase("f", 29), _phrase("1", 28), _phrase("2", 27)]
    extra = tuple(_adoption(10 + i, phrase, authors=(MEP_1,)) for i, phrase in enumerate(big))
    rows = review_rows(view(extra, tuple(big)), 6, seed=1, groups=GROUPS)
    assert [row.phrase_words for row in rows[:3]] == [30, 29, 28]
    sampled = [row for row in rows if row.selection == "sample"]
    assert len(sampled) == 3
    # Four more PPE verbatim claims exist, yet the sample takes one from each stratum in turn.
    assert {row.kind for row in sampled} == {"semantic", "verbatim"}
    assert len({(row.stage, row.kind, row.groups) for row in sampled}) == 3
    assert sum(row.groups == ("PPE",) for row in sampled) == 2


@given(n=st.integers(1, 9), seed=st.integers(0, 50))
def test_the_selection_is_deterministic_for_a_seed_and_every_row_is_in_the_view(
    n: int, seed: int
) -> None:
    lineage = view()
    claims = {
        claim_id(adoption.amendment_id, phrase_id)
        for adoption in lineage.adoptions
        for phrase_id in adoption.phrase_ids
    }
    first = review_rows(lineage, n, seed, GROUPS)
    assert first == review_rows(lineage, n, seed, GROUPS)
    assert {row.claim_id for row in first} <= claims
    assert len({row.claim_id for row in first}) == len(first) == min(n, len(claims))
    assert to_csv(first) == to_csv(review_rows(lineage, n, seed, GROUPS))


def test_the_csv_has_a_spanish_legend_then_a_header_and_one_row_per_claim() -> None:
    rows = review_rows(view(), 5, groups=GROUPS)
    text = to_csv(rows)
    assert text.startswith("# Leyenda:")
    table = list(csv.DictReader(io.StringIO(text.split("\n", 1)[1])))
    assert len(table) == 5
    by_id = {line["claim_id"]: line for line in table}
    big = by_id[claim_id("am:2099-0001-COD:IMCO:1", P_BIG.phrase_id)]
    assert big["groups"] == "PPE"
    assert big["similarity"] == ""
    assert "Acme (2099-01-05, precedes=True" in big["origins"]
    assert "undated" in big["origins"]
    assert by_id[claim_id("am:2099-0001-COD:IMCO:5", P_SEM.phrase_id)]["similarity"] == "0.900"
    assert by_id[claim_id("am:2099-0001-COD:IMCO:2", P_MID.phrase_id)]["origins"] == ""


def test_the_markdown_is_readable_and_says_when_nothing_was_found() -> None:
    text = to_markdown(review_rows(view(), 5, seed=7, groups=GROUPS), 7)
    assert "seed 7" in text
    assert "> Leyenda:" in text
    assert "coalition wording" in text
    assert "origin: none found" in text
    assert "committee text" in text
    assert "similarity: 0.900" in text
    assert "tabled 2099-03-01" in text


def test_the_markdown_marks_an_unknown_tabling_date() -> None:
    row = review_rows(view(), 1)[0].model_copy(update={"tabled_on": None})
    assert "tabled unknown" in to_markdown((row,), 0)


def test_export_writes_three_files_that_are_byte_identical_on_a_rerun(tmp_path: Path) -> None:
    rows = review_rows(view(), 5, seed=2, groups=GROUPS)
    out = tmp_path / "review"
    paths = export_rows(rows, 2, out)
    first = [path.read_bytes() for path in paths]
    assert [path.name for path in paths] == ["rows.jsonl", "rows.csv", "rows.md"]
    export_rows(rows, 2, out)
    assert [path.read_bytes() for path in paths] == first
    assert read_rows(paths[0]) == rows


def test_rows_with_an_invalid_line_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "rows.jsonl"
    path.write_text('{"claim_id": "x"}\n', encoding="utf-8")
    with pytest.raises(AuditError, match="invalid row"):
        read_rows(path)


def _row(key: str, kind: MatchKind = "verbatim") -> ReviewRow:
    return ReviewRow(
        claim_id=f"claim:{key}",
        selection="strongest",
        kind=kind,
        amendment_id=f"am:2099-0001-COD:IMCO:{key}",
        stage="committee",
        tabled_on=None,
        authors=(),
        groups=("committee_text",),
        phrase_words=12,
        similarity=None,
        shared_by_amendments=1,
        coalition=False,
        phrase="x",
        final_provision="art:x",
        final_quote="x",
        origins=(),
    )


def _label(key: str, reader: str, verdict: str, reason: str | None = None) -> LabelRecord:
    return LabelRecord.model_validate(
        {"claim_id": f"claim:{key}", "reader": reader, "verdict": verdict, "reason": reason}
    )


ROWS = (_row("1"), _row("2"), _row("3"), _row("4"), _row("5"), _row("6", "semantic"))


def test_precision_counts_only_claims_the_readers_agree_on() -> None:
    labels = [
        _label("1", "ana", "real"),
        _label("1", "ben", "real"),
        _label("2", "ana", "not_real"),
        _label("2", "ben", "not_real"),
        _label("3", "ana", "real"),
        _label("3", "ben", "not_real"),
        _label("4", "ana", "real"),
        _label("5", "ana", "unclear"),
        _label("5", "ben", "unclear"),
        _label("6", "ana", "real"),
        _label("6", "ben", "real", "same ask, other words"),
    ]
    summary = summarise(ROWS, labels)
    assert (summary.claims, summary.resolved, summary.real) == (6, 3, 2)
    assert (summary.unresolved, summary.unlabelled) == (2, 1)
    assert summary.precision == pytest.approx(2 / 3)
    assert (summary.low, summary.high) == wilson_interval(2, 3)
    assert summary.by_kind == {"semantic": (1, 1), "verbatim": (1, 2)}


def test_three_readers_must_all_agree_and_nobody_labelled_means_no_precision() -> None:
    three = [_label("1", reader, "real") for reader in ("ana", "ben", "cy")]
    assert summarise(ROWS[:1], three).resolved == 1
    split = [*three[:2], _label("1", "cy", "not_real")]
    assert summarise(ROWS[:1], split).unresolved == 1
    empty = summarise(ROWS, [])
    assert (empty.precision, empty.resolved, empty.unlabelled) == (None, 0, 6)
    assert (empty.low, empty.high) == (0.0, 1.0)


def test_labels_for_unknown_claims_or_repeated_by_a_reader_are_errors() -> None:
    with pytest.raises(AuditError, match="outside the review"):
        summarise(ROWS, [_label("99", "ana", "real")])
    with pytest.raises(AuditError, match="more than once"):
        summarise(ROWS, [_label("1", "ana", "real"), _label("1", "ana", "not_real")])


def test_labels_are_read_line_by_line_and_keep_unicode_separators(tmp_path: Path) -> None:
    path = tmp_path / "labels.jsonl"
    reason = "split here\N{LINE SEPARATOR}and here"
    record = _label("1", "ana", "real", reason)
    path.write_text(f"{record.model_dump_json()}\n\n{record.model_dump_json()}", encoding="utf-8")
    labels = read_labels(path)
    assert len(labels) == 2
    assert labels[0].reason == reason
    path.write_text(record.model_dump_json() + "\n" + '{"claim_id": "x"}\n', encoding="utf-8")
    with pytest.raises(AuditError, match="line 2 is invalid"):
        read_labels(path)


def _summary(resolved: int, real: int) -> ReviewSummary:
    low, high = wilson_interval(real, resolved)
    return ReviewSummary(
        claims=resolved,
        resolved=resolved,
        real=real,
        unresolved=0,
        unlabelled=0,
        precision=real / resolved if resolved else None,
        low=low,
        high=high,
        by_kind={},
    )


def test_the_gate_never_passes_on_too_few_or_no_resolved_labels() -> None:
    assert not meets_gate(_summary(0, 0), floor=0.0, minimum_resolved=1)
    assert not meets_gate(_summary(5, 5), floor=0.5, minimum_resolved=20)
    assert meets_gate(_summary(30, 30), floor=0.8, minimum_resolved=20)


def test_the_gate_uses_the_lower_end_of_the_interval_not_the_estimate() -> None:
    perfect_but_small = _summary(10, 10)
    assert perfect_but_small.precision == 1.0
    assert not meets_gate(perfect_but_small, floor=0.9, minimum_resolved=10)
    assert not meets_gate(_summary(30, 20), floor=0.9, minimum_resolved=20)


def test_the_gate_rejects_nonsense_settings() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        meets_gate(_summary(5, 5), floor=0.5, minimum_resolved=0)
    with pytest.raises(ValueError, match="between 0 and 1"):
        meets_gate(_summary(5, 5), floor=1.5, minimum_resolved=1)


def _write_view(path: Path) -> Path:
    path.write_text(view().model_dump_json(), encoding="utf-8")
    return path


def test_cli_export_prints_the_seed_and_writes_the_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _write_view(tmp_path / "lineage.json")
    groups = tmp_path / "groups.json"
    groups.write_text(json.dumps(GROUPS), encoding="utf-8")
    out = tmp_path / "review"
    args = ["export", "--view", str(source), "--out", str(out), "--n", "4", "--seed", "5"]
    assert main([*args, "--groups", str(groups)]) == 0
    printed = capsys.readouterr().out
    assert "4 claims selected (n 4, seed 5) from 2099/0001(COD)" in printed
    assert (out / "rows.csv").read_text(encoding="utf-8").startswith("# Leyenda:")
    assert "PPE" in (out / "rows.md").read_text(encoding="utf-8")


def test_cli_summarise_reports_and_gates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _write_view(tmp_path / "lineage.json")
    out = tmp_path / "review"
    assert main(["export", "--view", str(source), "--out", str(out), "--n", "3"]) == 0
    rows = read_rows(out / "rows.jsonl")
    labels = tmp_path / "labels.jsonl"
    lines = [
        _label(row.claim_id.removeprefix("claim:"), reader, "real").model_dump_json()
        for row in rows
        for reader in ("ana", "ben")
    ]
    labels.write_text("\n".join(lines) + "\n", encoding="utf-8")
    base = ["summarise", "--rows", str(out / "rows.jsonl"), "--labels", str(labels)]
    capsys.readouterr()
    assert main(base) == 0
    printed = capsys.readouterr().out
    assert "3 claims: 3 resolved, 0 unresolved, 0 unlabelled" in printed
    assert "precision 1.000" in printed
    assert "verbatim: 2 of 2 real" in printed
    assert "semantic: 1 of 1 real" in printed
    assert main([*base, "--floor", "0.3", "--minimum-resolved", "2"]) == 0
    assert "PASS" in capsys.readouterr().out
    assert main([*base, "--floor", "0.99", "--minimum-resolved", "2"]) == 3
    assert "FAIL" in capsys.readouterr().out
    labels.write_text("", encoding="utf-8")
    assert main(base) == 0
    assert "precision n/a" in capsys.readouterr().out


def test_cli_fails_cleanly_on_unusable_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["export", "--view", str(tmp_path / "missing.json"), "--out", str(tmp_path)]) == 1
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert main(["export", "--view", str(bad), "--out", str(tmp_path)]) == 1
    source = _write_view(tmp_path / "lineage.json")
    assert main(["export", "--view", str(source), "--out", str(tmp_path), "--n", "0"]) == 1
    assert capsys.readouterr().err.count("error:") == 3
    stray = tmp_path / "rows.jsonl"
    stray.write_text(_row("1").model_dump_json() + "\n", encoding="utf-8")
    labels = tmp_path / "labels.jsonl"
    labels.write_text(_label("2", "ana", "real").model_dump_json() + "\n", encoding="utf-8")
    assert main(["summarise", "--rows", str(stray), "--labels", str(labels)]) == 1
    assert "outside the review" in capsys.readouterr().err


def test_module_runs_as_a_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _write_view(tmp_path / "lineage.json")
    out = tmp_path / "review"
    argv = ["lineage_review", "export", "--view", str(source), "--out", str(out), "--n", "2"]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delitem(sys.modules, "influence.practice.lineage_review", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("influence.practice.lineage_review", run_name="__main__")
    assert exit_info.value.code == 0
    assert (out / "rows.md").exists()
