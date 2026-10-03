"""Blind-audit files: blind sheets, a seeded sample, two readers scored, a proposed threshold.

The view is the invented two-law fixture (`atlas_fixture`) with extra links copied from its
published and unconfirmed ones, so every sheet row joins real fixture records. The links,
scores and verdicts are made up: nothing here is evidence of precision.
"""

import csv
import io
import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from atlas_fixture import LAW_A, LAW_B, RETRIEVED, build_fixture

from influence.cli import main
from influence.schemas.atlas import LinkAssessment
from influence.schemas.atlas_view import AtlasBundleView, AtlasView
from influence.services.audit import Verdict
from influence.services.audit_sheets import (
    KEY_FILE,
    RESULT_FILE,
    SHEET_COLUMNS,
    SUMMARY_FILE,
    AuditFileError,
    AuditKey,
    propose_threshold,
    read_key,
    read_sheet,
    render_summary,
    score_sample,
    write_result,
    write_sample,
)
from influence.services.pipeline import write_view

SLUG = "2099-0001-COD"


def _fixture_links() -> dict[str, LinkAssessment]:
    return {link.link_id: link for link in build_fixture().links}


def _copies(
    link: LinkAssessment, count: int, prefix: str, **update: object
) -> list[LinkAssessment]:
    return [
        link.model_copy(update={"link_id": f"link:{prefix}{number:03d}", **update})
        for number in range(count)
    ]


def _view(links: Sequence[LinkAssessment]) -> AtlasView:
    fixture = build_fixture()
    return AtlasView(
        procedure_id=LAW_A,
        slug=SLUG,
        title="Fixture Regulation on widget safety",
        run_id="run-fixture",
        generated_at=RETRIEVED,
        ask_method="fixture",
        coverage=fixture.laws[0].coverage,
        bundle=AtlasBundleView(
            laws=fixture.laws,
            documents=fixture.documents,
            document_texts=(),
            passages=fixture.passages,
            actors=fixture.actors,
            asks=fixture.asks,
            amendments=fixture.amendments,
            articles=fixture.articles,
            links=tuple(links),
            outcomes=(),
        ),
        snapshot=fixture.graphs[0],
        rankings=(),
        limitations=(),
    )


def _world() -> AtlasView:
    """60 published links in three strata; 41 unconfirmed, 39 with scores spread over [0, 1)."""
    base = _fixture_links()
    makers, labels = base["link:a-am1-makers"], base["link:b-am3-labels"]
    city = base["link:a-am2-city"]
    return _view(
        [
            *base.values(),
            *_copies(makers, 40, "pc"),
            *_copies(makers, 12, "pr", tier="reworded"),
            *_copies(labels, 6, "pb"),
            *[
                link.model_copy(update={"support_score": number / 40})
                for number, link in enumerate(_copies(city, 39, "u"))
            ],
        ]
    )


def _rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"), newline="")))


def _fill(path: Path, verdict: Callable[[str], str]) -> None:
    rows = _rows(path)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows({**row, "verdict": verdict(row["item_id"])} for row in rows)
    path.write_text(buffer.getvalue(), encoding="utf-8")


def _links_by_item(directory: Path) -> dict[str, LinkAssessment]:
    return {item.item_id: item.link for item in read_key(directory).items}


# --- Sampling and blindness -----------------------------------------------------------------


def test_sheets_are_blind_identical_for_both_readers_and_join_real_records(tmp_path: Path) -> None:
    files = write_sample(_world(), tmp_path, size=40, seed=7)
    directory = files.directory
    assert directory == tmp_path / SLUG / "published-seed7-n40"
    sheet_a = (directory / "reader-a.csv").read_bytes()
    assert sheet_a == (directory / "reader-b.csv").read_bytes()
    rows = _rows(directory / "reader-a.csv")
    assert tuple(rows[0]) == SHEET_COLUMNS
    assert not {"score", "support_score", "tier", "status", "link_id"} & set(rows[0])
    text = sheet_a.decode("utf-8")
    # No link ID, tier, status or score leaks into the cells either.
    assert "link:" not in text
    assert not {"copied", "reworded", "published", "unconfirmed", "0.94", "0.81"} & set(
        text.replace(",", " ").split()
    )
    assert all(row["verdict"] == "" and row["note"] == "" for row in rows)
    assert len(rows) == 40
    assert {row["item_id"] for row in rows} == {item.item_id for item in files.key.items}
    makers = next(row for row in rows if row["amendment_id"].startswith("am:") and row["actor"])
    assert makers["ask_quote"]
    assert makers["ask_source_url"].startswith("https://")
    key = read_key(directory)
    assert key == files.key
    assert key.population == 60
    assert all(item.link.status == "published" for item in key.items)
    # Every stratum has a seat, and the seats follow the strata's sizes.
    seats = dict.fromkeys({item.stratum for item in key.items}, 0)
    for item in key.items:
        seats[item.stratum] += 1
    assert seats == {
        f"{LAW_A} copied": 27,
        f"{LAW_A} reworded": 8,
        f"{LAW_B} reworded": 5,
    }


def test_the_sample_is_a_function_of_the_seed(tmp_path: Path) -> None:
    first = write_sample(_world(), tmp_path / "one", size=20, seed=3).directory
    again = write_sample(_world(), tmp_path / "two", size=20, seed=3).directory
    other = write_sample(_world(), tmp_path / "three", size=20, seed=4).directory
    assert (first / KEY_FILE).read_bytes() == (again / KEY_FILE).read_bytes()
    assert (first / "reader-a.csv").read_bytes() == (again / "reader-a.csv").read_bytes()
    assert _links_by_item(first) != _links_by_item(other)


def test_unconfirmed_and_tier_samples_draw_only_those_links(tmp_path: Path) -> None:
    files = write_sample(_world(), tmp_path, size=10, seed=1, status="unconfirmed")
    assert files.directory.name == "unconfirmed-seed1-n10"
    assert files.key.purpose.startswith("PROPOSED re-scope")
    assert {item.link.status for item in files.key.items} == {"unconfirmed"}
    assert files.key.population == 41
    reworded = write_sample(_world(), tmp_path, size=10, seed=1, tier="reworded")
    assert reworded.directory.name == "published-reworded-seed1-n10"
    assert {item.link.tier for item in reworded.key.items} == {"reworded"}
    assert reworded.key.population == 19


def test_an_existing_sample_an_empty_population_and_a_dangling_link_are_refused(
    tmp_path: Path,
) -> None:
    write_sample(_world(), tmp_path, size=5, seed=1)
    with pytest.raises(AuditFileError, match="already exists"):
        write_sample(_world(), tmp_path, size=5, seed=1)
    base = _fixture_links()
    with pytest.raises(AuditFileError, match="no unconfirmed links of tier reworded"):
        write_sample(
            _view(list(base.values())),
            tmp_path,
            size=5,
            seed=1,
            status="unconfirmed",
            tier="reworded",
        )
    ghost = base["link:a-am1-makers"].model_copy(update={"ask_id": "ask:ghost"})
    with pytest.raises(AuditFileError, match="lacks record 'ask:ghost'"):
        write_sample(_view([ghost]), tmp_path / "ghost", size=5, seed=1)
    assert not (tmp_path / "ghost" / SLUG / "published-seed1-n5" / KEY_FILE).exists()


# --- Scoring --------------------------------------------------------------------------------


def test_scoring_counts_agreements_and_splits_per_stratum(tmp_path: Path) -> None:
    directory = write_sample(_world(), tmp_path, size=40, seed=7).directory
    links = _links_by_item(directory)
    items = sorted(links)
    split = set(items[:4])
    # Reader A says yes to every copied link and to the split items; B says yes to copied
    # links only, and "unsure" counts as no.
    _fill(
        directory / "reader-a.csv",
        lambda item: "yes" if links[item].tier == "copied" or item in split else "no",
    )
    _fill(
        directory / "reader-b.csv",
        lambda item: "Yes" if links[item].tier == "copied" and item not in split else "unsure",
    )
    result = score_sample(directory)
    assert result.overall.disagreements == 4
    copied = sum(1 for link in links.values() if link.tier == "copied")
    split_copied = sum(1 for item in split if links[item].tier == "copied")
    assert result.overall.agreed_correct == copied - split_copied
    assert result.overall.agreed_incorrect == 40 - copied - (4 - split_copied)
    assert result.overall.precision == pytest.approx(result.overall.agreed_correct / 40)
    assert result.overall.low < result.overall.agreed_correct / 40 < result.overall.high
    by_stratum = {row.stratum: row for row in result.strata}
    assert set(by_stratum) == {f"{LAW_A} copied", f"{LAW_A} reworded", f"{LAW_B} reworded"}
    assert sum(row.sampled for row in result.strata) == 40
    assert by_stratum[f"{LAW_B} reworded"].agreed_correct == 0
    assert result.threshold is None
    assert not result.clears_floor
    view_before = json.dumps(_world().model_dump(mode="json"))
    data, summary = write_result(result, directory)
    assert json.loads(data.read_text())["overall"]["disagreements"] == 4
    assert "| all | 40 |" in summary.read_text()
    assert "does not reach the floor of 0.90" in summary.read_text()
    assert json.dumps(_world().model_dump(mode="json")) == view_before


def test_blank_verdicts_are_unlabelled_not_wrong(tmp_path: Path) -> None:
    directory = write_sample(_world(), tmp_path, size=6, seed=2).directory
    result = score_sample(directory)
    assert result.overall.unlabelled == 6
    assert result.overall.precision is None
    assert (result.overall.low, result.overall.high) == (0.0, 1.0)
    assert "| n/a |" in render_summary(result)


def test_an_unconfirmed_sample_proposes_the_lowest_cut_that_clears_the_floor(
    tmp_path: Path,
) -> None:
    city = _fixture_links()["link:a-am2-city"]
    strong = _copies(city, 50, "s", support_score=0.9)
    weak = _copies(city, 10, "w", support_score=0.3)
    directory = write_sample(
        _view([*strong, *weak]), tmp_path, size=60, seed=5, status="unconfirmed"
    ).directory
    links = _links_by_item(directory)
    for reader in ("a", "b"):
        _fill(
            directory / f"reader-{reader}.csv",
            lambda item: "yes" if links[item].support_score >= 0.5 else "no",
        )
    result = score_sample(directory)
    assert result.threshold is not None
    cuts = {row.cut: row for row in result.threshold.cuts}
    assert (cuts[0.3].judged, cuts[0.3].correct) == (60, 50)
    assert cuts[0.3].low < 0.9 <= cuts[0.35].low
    assert (cuts[0.95].judged, cuts[0.95].precision) == (0, None)
    assert result.threshold.proposed_cut == 0.35
    assert "PROPOSAL only" in result.threshold.note
    summary = render_summary(result)
    assert "## Proposed prose threshold" in summary
    assert "The lowest cut is 0.35, which reaches a lower bound of 0.90." in summary


def test_no_cut_is_proposed_when_none_clears_the_floor() -> None:
    city = _fixture_links()["link:a-am2-city"]
    links = _copies(city, 10, "x", support_score=0.9)
    labels: dict[str, dict[str, Verdict]] = {
        link.link_id: {"a": "correct", "b": "correct"} for link in links
    }
    proposal = propose_threshold(links, labels)
    assert proposal.proposed_cut is None
    assert all(row.low < 0.9 for row in proposal.cuts)


# --- Invalid files --------------------------------------------------------------------------


def test_missing_and_invalid_files_are_explicit_errors(tmp_path: Path) -> None:
    directory = write_sample(_world(), tmp_path, size=4, seed=1).directory
    ids = [item.item_id for item in read_key(directory).items]
    sheet = directory / "reader-a.csv"
    with pytest.raises(AuditFileError, match="Cannot read the sheet"):
        read_sheet(directory / "absent.csv", ids)
    sheet.write_text("item_id,note\nitem-001,x\n", encoding="utf-8")
    with pytest.raises(AuditFileError, match=r"lacks the column\(s\) \['verdict'\]"):
        read_sheet(sheet, ids)
    sheet.write_text("item_id,verdict\nitem-999,yes\n", encoding="utf-8")
    with pytest.raises(AuditFileError, match=r"unknown \['item-999'\]"):
        read_sheet(sheet, ids)
    rows = "".join(f"{item},maybe\n" for item in ids)
    sheet.write_text(f"item_id,verdict\n{rows}", encoding="utf-8")
    with pytest.raises(AuditFileError, match="other than yes, no, unsure or blank"):
        read_sheet(sheet, ids)
    # A spreadsheet's byte-order mark and short rows are read, not rejected.
    rows = "".join(f"{item}\n" for item in ids[1:])
    sheet.write_text(f"﻿item_id,verdict\n{ids[0]},no\n{rows}", encoding="utf-8")
    assert read_sheet(sheet, ids) == {ids[0]: "incorrect"}
    (directory / KEY_FILE).write_text("{}", encoding="utf-8")
    with pytest.raises(AuditFileError, match="is invalid"):
        read_key(directory)
    with pytest.raises(AuditFileError, match="Cannot read the key"):
        read_key(tmp_path / "nowhere")
    assert AuditKey.model_fields["items"].is_required()


# --- The command ----------------------------------------------------------------------------


def test_audit_commands_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_view(_world(), tmp_path / "laws" / SLUG)
    view_bytes = (tmp_path / "laws" / SLUG / "atlas.json").read_bytes()
    root = ["--data-root", str(tmp_path)]
    assert main(["audit", "sample", LAW_A, "--size", "8", "--seed", "11", *root]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"Sampled 8 of 60 published links of {LAW_A} (run run-fixture)")
    directory = tmp_path / "audit" / SLUG / "published-seed11-n8"
    assert f"reader a: {directory / 'reader-a.csv'}" in out
    for reader in ("a", "b"):
        _fill(directory / f"reader-{reader}.csv", lambda _item: "yes")
    assert main(["audit", "score", str(directory)]) == 0
    out = capsys.readouterr().out
    assert "  all: 8 agreed correct, 0 agreed incorrect, 0 split, 0 unlabelled" in out
    assert "Proposed prose threshold" not in out
    assert (directory / RESULT_FILE).is_file()
    assert (directory / SUMMARY_FILE).is_file()

    assert main(["audit", "sample", SLUG, "--seed", "1", "--status", "unconfirmed", *root]) == 0
    capsys.readouterr()
    unconfirmed = tmp_path / "audit" / SLUG / "unconfirmed-seed1-n40"
    assert main(["audit", "score", str(unconfirmed)]) == 0
    out = capsys.readouterr().out
    assert "precision n/a (95% 0.000 to 1.000)" in out
    assert "Proposed prose threshold (a proposal, not applied): none reaches" in out
    # The audit never writes into the law's view.
    assert (tmp_path / "laws" / SLUG / "atlas.json").read_bytes() == view_bytes


def test_audit_command_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = ["--data-root", str(tmp_path)]
    assert main(["audit", "sample", "2099/0009(COD)", "--seed", "1", *root]) == 1
    assert "No atlas view at" in capsys.readouterr().err
    assert main(["audit", "score", str(tmp_path / "nothing")]) == 1
    assert "Cannot read the key" in capsys.readouterr().err
    with pytest.raises(SystemExit) as stopped:
        main(["audit", "sample", "///", "--seed", "1"])
    assert stopped.value.code == 2
    assert "no usable characters" in capsys.readouterr().err
