"""The public report: built only from what the other commands wrote, counted as "N of M".

The full world is `test_pipeline`'s matching world (one genuinely matching ask and
amendment, and a final-act provision holding the asked-for wording) with every file the
other commands write beside its collected bundle. Smaller cases build `LawFiles` directly.
"""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_lineage_assembly import collected as lineage_collected
from test_pipeline import AI_ACT, LATER, RARE, SLUG, matching_world, with_final_wording

from influence import cli
from influence.schemas.atlas import Forecast, SourceSpan
from influence.schemas.atlas_view import RankingRow
from influence.schemas.coordinated import ClusterMember, CoordinatedCluster
from influence.services import pipeline, report
from influence.services.channels import build_channels, write_channels
from influence.services.coordinated import build_coordination, write_coordination
from influence.services.direction import build_directions, write_directions
from influence.services.lineage_assembly import build_lineage, write_lineage
from influence.services.report import LawFiles, ReportError

NOW = datetime(2026, 10, 3, 18, 0, tzinfo=UTC)


def full_world(tmp_path: Path, *, publish: bool = True) -> Path:
    """Collect, then write every file `influence report` reads; returns the data root."""
    bundle = matching_world(tmp_path).collect().bundle
    law = pipeline.load_collected(bundle)
    view = pipeline.build_view(with_final_wording(law), generated_at=LATER, publish_prose=publish)
    pipeline.write_view(view, bundle)
    run = law.manifest.run_id
    clusters = build_coordination(law.law, run, law.amendments, law.actors, generated_at=LATER)
    write_coordination(clusters, bundle)
    channels = build_channels(
        law.law,
        run,
        documents=law.documents,
        passages=law.passages,
        actors=law.actors,
        amendments=law.amendments,
        types=None,
        generated_at=LATER,
    )
    write_channels(channels, bundle)
    directions = build_directions(
        law.law, run, law.amendments, law.actors, view, generated_at=LATER
    )
    write_directions(directions, bundle)
    write_lineage(build_lineage(law, generated_at=LATER), bundle)
    return tmp_path


def markdown(laws: list[LawFiles], links: int = 3, seed: int = 1) -> str:
    return report.build_report(laws, generated_at=NOW, links=links, seed=seed).markdown


def section(text: str, heading: str) -> str:
    """One `## ` section of the report, up to the next."""
    start = text.index(f"## {heading}")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else None]


# --- Counting -------------------------------------------------------------------------------


def test_counts_are_written_with_their_denominator() -> None:
    assert report.of(4, 37) == "4 of 37"
    assert report.of(1234, 56789) == "1,234 of 56,789"


@given(st.lists(st.integers(), max_size=30, unique=True), st.integers(1, 10), st.integers())
def test_the_link_sample_is_seeded_uniform_and_without_repeats(
    items: list[int], count: int, seed: int
) -> None:
    drawn = report.sample(items, count, seed)
    assert drawn == report.sample(items, count, seed), f"seed {seed}"
    assert len(drawn) == min(count, len(items))
    assert len(set(drawn)) == len(drawn)
    assert set(drawn) <= set(items)


def test_competition_ranks_share_ties() -> None:
    assert report.ranks([5.0, 9.0, 5.0, 1.0]) == [2, 1, 2, 4]


# --- The full world -------------------------------------------------------------------------


def test_every_question_has_a_headline_evidence_and_a_limitation(tmp_path: Path) -> None:
    root = full_world(tmp_path)
    law = report.load_law(root, SLUG)
    text = markdown([law])

    assert text.startswith("# influence: who shaped Artificial Intelligence Act\n")
    for heading in ("WHO wins", "WHAT they win", "TOWARDS what", "HOW they win"):
        body = section(text, heading)
        assert "Headline: " in body, heading
        assert "Evidence: " in body or "`data/laws/" in body, heading
        assert "- Limitation: " in body, heading
    assert "%" not in text[: text.index("## Methods")]
    coverage = section(text, "Coverage")
    assert f"({AI_ACT}), collect run `{law.collected.manifest.run_id}`" in coverage
    assert "meetings (" in coverage
    assert "Not run" not in coverage
    who = section(text, "WHO wins")
    assert "Headline: 0 of 3 actors with asks have at least 3 assessed" in who
    assert "1 of 1 shown links are published" in who
    assert "No actor has 3 or more assessed asks" in who
    assert "Lineage: " in who
    assert "No validated forecast; reasoned scenarios only" in section(text, "NEXT")
    assert "0 of 3 actors with asks have both 3 or more assessed asks" in text


def test_three_random_links_quote_ask_amendment_and_final_act_side_by_side(
    tmp_path: Path,
) -> None:
    law = report.load_law(full_world(tmp_path), SLUG)
    built = report.build_report([law], generated_at=NOW, links=3, seed=7)
    links = "\n".join(built.links)

    assert "Drawn 1 of 1 published links." in links
    assert "--links 3 --seed 7" in links
    assert links.count(RARE) >= 3  # the ask, the amendment and the final act
    assert "**Ask**, submitted " in links
    assert "**Amendment** `am:2021-0106-COD:ENVI:PE7-7`, tabled " in links
    assert "**Final act** (full, Article 99(1)" in links
    assert "Source: https://" in links
    assert built.links == report.build_report([law], generated_at=NOW, links=3, seed=7).links
    assert any(line.startswith("WHO wins") for line in built.headlines)


def test_an_untraced_link_says_so(tmp_path: Path) -> None:
    root = full_world(tmp_path)
    law = report.load_law(root, SLUG)
    assert law.view is not None
    view = law.view.model_copy(
        update={"bundle": law.view.bundle.model_copy(update={"outcomes": ()})}
    )
    text = markdown([replace(law, view=view)])
    assert "**Final act**: not traced through this amendment to the final act." in text


def test_no_published_link_falls_back_to_labelled_lineage_adoptions(tmp_path: Path) -> None:
    law = report.load_law(full_world(tmp_path, publish=False), SLUG)
    lineage_law = lineage_collected()
    lineage = build_lineage(lineage_law, generated_at=NOW)
    fallback = LawFiles(
        slug="2099-0001-COD",
        collected=lineage_law,
        view=None,
        coordinated=None,
        channels=None,
        directions=None,
        lineage=lineage,
        forecasts=None,
        problems=(),
    )
    text = markdown([law, fallback])

    assert text.startswith("# influence: who shaped 2 EU laws\n")
    links = section(text, "Links side by side")
    assert "0 published links across 1 of 2 laws with an atlas view." in links
    assert "**not published links**: 1 of 1 verbatim adoptions" in links
    assert "NOT a published link" in links
    assert "**Amendment** `am:2099-0001-COD:IMCO:1`" in links
    assert "No actor directions (no_published_links)" in section(text, "TOWARDS what")
    # A carrier missing from the bundle, and a phrase with no carrier, are said, not hidden.
    phrase = lineage.adopted_phrases[0]
    orphan = replace(fallback, collected=replace(lineage_law, amendments=()))
    assert "not in the collected bundle" in "\n".join(
        report.phrase_card(1, orphan, lineage, phrase)
    )
    alone = lineage.model_copy(update={"adoptions": (), "credits": (), "origins": ()})
    assert "no carrying amendment listed" in "\n".join(
        report.phrase_card(1, fallback, alone, phrase)
    )


# --- Missing, stale and invalid files -------------------------------------------------------


def bare(tmp_path: Path) -> LawFiles:
    matching_world(tmp_path).collect()
    return report.load_law(tmp_path, SLUG)


def test_missing_files_are_named_with_the_command_that_writes_them(tmp_path: Path) -> None:
    text = markdown([bare(tmp_path)])

    for name, command in report.FILES:
        assert (
            f"Not run: `data/laws/{SLUG}/{name}` is missing; run `make {command} LAW='{AI_ACT}'`."
        ) in text
    assert "0 published links across 0 of 1 laws with an atlas view." in text
    assert "No lineage adopted phrase to show instead." in text
    assert "Headline" not in text


def test_stale_and_invalid_files_are_flagged_not_used(tmp_path: Path) -> None:
    root = full_world(tmp_path)
    bundle = root / "laws" / SLUG
    (bundle / "channels.json").write_text("{}")
    (root / "laws" / "forecast.json").write_text("not json")
    law = report.load_law(root, SLUG)
    assert law.coordinated is not None
    stale = replace(law, coordinated=law.coordinated.model_copy(update={"run_id": "run:old"}))
    text = markdown([stale])

    assert "`coordinated.json` was built from an older collect run `run:old`." in text
    assert "`channels.json` is invalid and was not used" in text
    assert f"Not used: `data/laws/{SLUG}/channels.json` is invalid; rerun `make channels" in text
    assert "`forecast.json` is invalid and was not used" in text


def test_a_law_never_collected_or_unnamed_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ReportError, match="make atlas"):
        report.load_law(tmp_path, SLUG)
    with pytest.raises(ReportError, match="at least one law"):
        report.build_report([], generated_at=NOW, links=1, seed=1)


# --- Sections from hand-made records --------------------------------------------------------


def test_rankings_and_spend_are_shown_side_by_side_with_ranks(tmp_path: Path) -> None:
    law = report.load_law(full_world(tmp_path), SLUG)
    assert law.view is not None
    actors = law.collected.actors[:3]
    rows = tuple(
        RankingRow(
            actor_id=actor.actor_id,
            actor_name=actor.name,
            observed_asks=5,
            assessed_asks=4,
            full=full,
            partial=1,
            not_observed=3 - full,
            unknown=1,
            evidence_record_ids=(f"outcome:{index}",),
        )
        for index, (actor, full) in enumerate(zip(actors, (2, 1, 0), strict=True))
    )
    costs = (10_000.0, 90_000.0, None)
    spending = tuple(
        actor.model_copy(update={"declared_cost_eur": cost})
        for actor, cost in zip(actors, costs, strict=True)
    )
    view = law.view.model_copy(update={"rankings": rows})
    text = markdown([replace(law, view=view, collected=replace(law.collected, actors=spending))])

    who = section(text, "WHO wins")
    assert "Headline: 3 of 3 actors with asks have at least 3 assessed" in who
    assert f"{actors[0].name}: full wins in 2 of 4 assessed asks (partial 1; 1 unknown" in who
    assert f"Evidence: `data/laws/{SLUG}/atlas.json`, field `rankings`; " in who
    assert "`outcome:0`" in who
    spend = section(text, "Wins and declared spend")
    assert f"| {actors[0].name} | 2 of 4 | 1 | 10,000 | 2 |" in spend
    assert f"| {actors[1].name} | 1 of 4 | 2 | 90,000 | 1 |" in spend
    assert actors[2].name not in spend


def test_a_cross_group_cluster_is_quoted_with_both_groups(tmp_path: Path) -> None:
    law = report.load_law(full_world(tmp_path), SLUG)
    assert law.coordinated is not None

    def member(number: int, group: str) -> ClusterMember:
        wording = "shared wording drafted outside the Parliament for every group"
        return ClusterMember(
            amendment_id=f"am:{SLUG}:ENVI:{number}",
            stage="committee",
            committee="ENVI",
            tabled_on=None,
            target_provision=None,
            author_ids=(f"actor:mep:{number}",),
            author_names=(f"Member {number}",),
            political_groups=(group,),
            inserted=(
                SourceSpan(
                    record_id=f"am:{SLUG}:ENVI:{number}",
                    field="new_text",
                    start=0,
                    end=len(wording),
                    text=wording,
                ),
            ),
        )

    cluster = CoordinatedCluster(
        cluster_id="cluster:1",
        members=(member(1, "PPE"), member(2, "S&D")),
        political_groups=("PPE", "S&D"),
        cross_group=True,
        inserted_words=9,
        min_similarity=1.0,
    )
    coordinated = law.coordinated.model_copy(update={"clusters": (cluster,)})
    what = section(markdown([replace(law, coordinated=coordinated)]), "WHAT they win")

    assert "Coordinated amendments: 1 of 1 clusters" in what
    assert "Example `cluster:1`: 2 amendments by PPE and S&D, at least 9 shared" in what
    assert f"`am:{SLUG}:ENVI:2` [S&D]: " in what


def test_lineage_credits_counts_and_unknown_adoption() -> None:
    law = lineage_collected()
    lineage = build_lineage(law, generated_at=NOW)
    files = LawFiles(
        slug="2099-0001-COD",
        collected=law,
        view=None,
        coordinated=None,
        channels=None,
        directions=None,
        lineage=lineage,
        forecasts=None,
        problems=(),
    )
    text = markdown([files])
    assert "Members: " in text
    assert "adopted 1 of 1 amendments tabled; 1 phrase(s), 0 joint" in text
    assert "Headline: " in section(text, "WHAT they win")
    assert "Longest: " in text

    uncounted = lineage.model_copy(
        update={
            "counts": lineage.counts.model_copy(update={"linked_units": None}),
            "adopted_phrases": (),
            "adoptions": (),
            "credits": (),
            "origins": (),
            "tabled_phrases": (),
        }
    )
    what = section(markdown([replace(files, lineage=uncounted)]), "WHAT they win")
    assert "Headline: not counted new words" in what
    assert "Longest" not in what
    unknown = uncounted.model_copy(update={"status": "unknown", "reason": "no final act"})
    text = markdown([replace(files, lineage=unknown)])
    assert "Adopted wording: unknown, no final act" in text
    assert "who put wording into the final act): unknown, no final act" in text


def forecast(score: float | None) -> Forecast:
    return Forecast(
        forecast_id="forecast:ask-1",
        procedure_id=AI_ACT,
        ask_id="ask:1",
        as_of=NOW,
        event="The requested wording appears in the next stage of the law",
        score_type="scenario" if score is None else "probability",
        score=score,
        scenario="Plausible only if the amendment is adopted" if score is None else None,
        reasons=("1 amendment(s) carry the ask.",),
        model_revision="group-rates-1",
    )


def test_next_reads_the_shared_forecast_file_for_this_law(tmp_path: Path) -> None:
    root = full_world(tmp_path)
    other = forecast(0.4).model_copy(update={"procedure_id": "2099/0001(COD)"})
    file = report.ForecastFile(forecasts=(forecast(None), other))
    (root / "laws" / "forecast.json").write_text(
        file.model_dump_json()[:-1] + ', "validation": {"adequate": false}}'
    )
    nxt = section(markdown([report.load_law(root, SLUG)]), "NEXT")
    assert "Headline: 0 of 1 forecasts carry a validated probability; no validated" in nxt
    assert "`ask:1`: scenario Plausible only if the amendment is adopted (group-rates-1)" in nxt

    scored = report.ForecastFile(forecasts=(forecast(0.62),))
    (root / "laws" / "forecast.json").write_text(scored.model_dump_json())
    nxt = section(markdown([report.load_law(root, SLUG)]), "NEXT")
    assert "Headline: 1 of 1 forecasts carry a validated probability." in nxt
    assert "`ask:1`: probability 0.62" in nxt


# --- Naming laws ----------------------------------------------------------------------------


def test_a_law_is_named_by_slug_number_title_alias_or_celex(tmp_path: Path) -> None:
    root = full_world(tmp_path)
    (root / "laws" / "stray").mkdir()
    celex = report.load_law(root, SLUG).law.celex_final
    assert celex is not None
    for query in (SLUG, AI_ACT, "2021/106(cod)", "Artificial Intelligence Act", "AI Act", celex):
        assert report.resolve_slug(root, query) == SLUG, query
    for query in ("Toy Safety", "32099R9999"):
        with pytest.raises(ReportError, match="no single collected law"):
            report.resolve_slug(root, query)
    with pytest.raises(ReportError, match="empty"):
        report.resolve_slug(root, "  ")


# --- The command ----------------------------------------------------------------------------


def test_the_command_writes_the_report_and_prints_the_link_sample(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = full_world(tmp_path)
    out = tmp_path / "out" / "report.md"

    status = cli.main(
        [
            *("report", f"{AI_ACT}, {SLUG}", "--data-root", str(root), "--out", str(out)),
            *("--links", "2", "--seed", "11"),
        ]
    )

    printed = capsys.readouterr().out
    assert status == 0
    assert f"report: {out.absolute()}" in printed
    assert "Drawn 1 of 1 published links." in printed
    assert "WHO wins" in printed
    written = out.read_text()
    # Both spellings name one law: it is reported once.
    assert written.startswith("# influence: who shaped Artificial Intelligence Act\n")
    assert "--links 2 --seed 11" in written
    assert list(out.parent.iterdir()) == [out]

    assert cli.main(["report", AI_ACT, "--data-root", str(root)]) == 0
    assert (root / "laws" / report.REPORT_FILE).is_file()


def test_the_command_writes_nothing_when_a_law_cannot_be_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = full_world(tmp_path)

    assert cli.main(["report", "No Such Law", "--data-root", str(root)]) == 1
    assert "No report was written." in capsys.readouterr().err
    # An output path that is a directory cannot be replaced.
    assert cli.main(["report", AI_ACT, "--data-root", str(root), "--out", str(root)]) == 1
    assert not (root / "laws" / report.REPORT_FILE).exists()
