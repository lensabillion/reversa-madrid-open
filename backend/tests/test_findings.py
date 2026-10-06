"""`report.law_findings`: the report's five questions for one law, as data.

The worlds are `test_report`'s: the full world writes every file the report reads, the bare
world only the collected bundle. Each finding must carry exactly the report's own lines.
"""

from pathlib import Path

import pytest
from test_pipeline import AI_ACT, SLUG
from test_report import bare, forecast, full_world, markdown

from influence.schemas.findings import LawFindings
from influence.services import report


def findings(root: Path, slug: str = SLUG) -> LawFindings:
    # Through JSON and back, as a reader of the file would see it.
    answer = report.law_findings(report.load_law(root, slug))
    return LawFindings.model_validate_json(answer.model_dump_json())


def test_every_computed_question_carries_the_report_headline_evidence_and_limitation(
    tmp_path: Path,
) -> None:
    root = full_world(tmp_path)
    answer = findings(root)
    text = markdown([report.load_law(root, SLUG)])

    assert (answer.procedure_id, answer.slug, answer.title) == (
        AI_ACT,
        SLUG,
        "Artificial Intelligence Act",
    )
    assert [f.question for f in answer.findings] == ["WHO", "WHAT", "TOWARDS", "HOW", "NEXT"]
    computed = answer.findings[:4]
    for item in computed:
        assert item.status == "computed", item.question
        assert item.command is None
        assert item.notes == ()
        assert f"- Headline: {item.headline}" in text
        assert f"- Limitation: {item.limitation}" in text
        assert all(f"- {line}" in text or f"  - {line}" in text for line in item.details)
        labels = ("Headline", "Limitation", "Evidence")
        assert not any(line.startswith(labels) for line in item.details)
    who, what, towards, how, _ = answer.findings
    assert (who.headline or "").startswith("0 of 3 actors with asks")
    assert [(e.file, e.field) for e in who.evidence] == [
        (f"data/laws/{SLUG}/atlas.json", "rankings"),
        (f"data/laws/{SLUG}/lineage.json", "credits"),
    ]
    # Lineage is cited in no WHAT line, yet it is read, so it is evidence too.
    assert {(e.file, e.field) for e in what.evidence} == {
        (f"data/laws/{SLUG}/coordinated.json", "clusters"),
        (f"data/laws/{SLUG}/lineage.json", None),
    }
    assert [e.file for e in towards.evidence] == [f"data/laws/{SLUG}/directions.json"]
    assert [e.file for e in how.evidence] == [f"data/laws/{SLUG}/channels.json"]


def test_a_question_whose_files_are_missing_names_the_command_that_writes_them(
    tmp_path: Path,
) -> None:
    bare(tmp_path)
    answer = findings(tmp_path)

    commands = {f.question: f.command for f in answer.findings}
    assert commands == {
        "WHO": f"make atlas LAW='{AI_ACT}'",
        "WHAT": f"make lineage LAW='{AI_ACT}'",
        "TOWARDS": f"make directions LAW='{AI_ACT}'",
        "HOW": f"make channels LAW='{AI_ACT}'",
        "NEXT": f"make forecast LAW='{AI_ACT}'",
    }
    for item in answer.findings:
        assert item.status == "not_run"
        assert (item.headline, item.details, item.evidence) == (None, (), ())
        assert item.limitation
        assert item.notes[0].startswith("Not run: ")
        assert f"`{item.command}`" in item.notes[0]
    assert answer.findings[-1].notes == (
        f"Not run: `data/laws/forecast.json` is missing; run `make forecast LAW='{AI_ACT}'`.",
    )


def test_who_falls_back_to_lineage_credits_when_the_atlas_view_is_missing(
    tmp_path: Path,
) -> None:
    root = full_world(tmp_path)
    (root / "laws" / SLUG / "atlas.json").unlink()
    who = findings(root).findings[0]

    assert who.status == "computed"
    assert (who.headline or "").startswith("Lineage: ")
    assert who.notes == (
        f"Not run: `data/laws/{SLUG}/atlas.json` is missing; run `make atlas LAW='{AI_ACT}'`.",
    )
    assert [e.file for e in who.evidence] == [f"data/laws/{SLUG}/lineage.json"]


def test_an_invalid_file_is_not_run_and_a_written_forecast_is_computed(tmp_path: Path) -> None:
    root = full_world(tmp_path)
    (root / "laws" / SLUG / "channels.json").write_text("{}")
    file = report.ForecastFile(forecasts=(forecast(0.62),))
    (root / "laws" / "forecast.json").write_text(file.model_dump_json())
    *_, how, nxt = findings(root).findings

    assert how.status == "not_run"
    assert how.notes[0].startswith(f"Not used: `data/laws/{SLUG}/channels.json` is invalid")
    assert nxt.status == "computed"
    assert nxt.headline == "1 of 1 forecasts carry a validated probability."
    assert [(e.file, e.field) for e in nxt.evidence] == [("data/laws/forecast.json", "forecasts")]


def test_a_law_never_collected_names_the_command_that_collects_it(tmp_path: Path) -> None:
    with pytest.raises(report.ReportError, match="make atlas"):
        report.load_law(tmp_path, SLUG)
