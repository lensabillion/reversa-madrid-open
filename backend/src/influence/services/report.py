"""Part 8's public report: one Markdown file built only from files other commands wrote.

`influence report <law> [<law> ...]` reads, for each law, the collected bundle (for the
register's declared spend and the source URLs) and the files under `data/laws/<slug>/`:
`atlas.json`, `coordinated.json`, `channels.json`, `directions.json`, `lineage.json` and,
when another command has written it, `forecast.json`. It computes nothing new: every
number is a count already in one of those files, written as "N of M" with its denominator
(`docs/plan.md` section 7), and a file that is missing is named with the command that
writes it instead of being guessed. The report is written atomically, so a generated
number is never edited by hand.

The five questions of the brief (WHO, WHAT, TOWARDS, HOW, NEXT) each get a headline
number, a named actor or law, evidence references and one limitation. The jury's check
("pick three links at random and read both texts side by side") is a seeded uniform
sample of published links, printed with the exact quoted spans and their sources.
"""

import random
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from influence.extraction.files import write_bytes_atomic
from influence.extraction.layout import procedure_slug
from influence.extraction.records import StageStore
from influence.schemas.atlas import (
    Actor,
    Amendment,
    Forecast,
    LawRecord,
    LayerCoverage,
    LinkAssessment,
    SourceSpan,
)
from influence.schemas.atlas_view import SLUG_PATTERN, AtlasView, RankingRow
from influence.schemas.channels import ChannelsView
from influence.schemas.coordinated import CoordinatedView
from influence.schemas.directions import DirectionCounts, DirectionsView
from influence.schemas.findings import EvidenceRef, Finding, LawFindings, Question
from influence.schemas.lineage import MIN_ADOPTED_RUN_WORDS, AdoptedPhrase, LineageView
from influence.services import assessment, coordinated
from influence.services.atlas_analysis import MIN_ASSESSED_ASKS
from influence.services.law_query import LAW_ALIASES, parse_query, resolve_title
from influence.services.pipeline import Collected, PipelineError, load_collected

REPORT_FILE = "report.md"
FORECAST_FILE = "forecast.json"
DEFAULT_LINKS = 3
DEFAULT_SEED = 20261003
# Rows each table shows; the files hold all of them.
TOP = 5
# How much of an amendment's new wording a lineage card quotes; the span itself is whole.
WORDING_CHARACTERS = 600
FILES = (
    ("atlas.json", "atlas"),
    ("coordinated.json", "coordinated"),
    ("channels.json", "channels"),
    ("directions.json", "directions"),
    ("lineage.json", "lineage"),
)
CUT = (
    "Public-voice cards (what an actor says in public against what it asks) are not built.",
    "The batch of every law since 2019 is not run: the report covers only the laws named.",
    "Meetings with Commissioners and MEPs are not collected, so a missing meeting is not "
    "missing influence.",
    "Roll-call votes are not collected.",
    "Parliament's position is not traced as its own stage; outcomes are read against the "
    "final act.",
)


class ReportError(RuntimeError):
    """A named law cannot be reported: it is unknown here or was never collected."""


def of(part: int, whole: int) -> str:
    """The plan's counting form: "4 of 37", never a bare percentage."""
    return f"{part:,} of {whole:,}"


def _quote(text: str) -> str:
    """One line of Markdown quotation; only runs of whitespace are folded."""
    return '"' + " ".join(text.split()) + '"'


def _span(span: SourceSpan) -> str:
    return f"{_quote(span.text)} (`{span.record_id}` {span.field} [{span.start}, {span.end}))"


@dataclass(frozen=True)
class LawFiles:
    """What the other commands wrote for one law; None is "not written", never empty."""

    slug: str
    collected: Collected
    view: AtlasView | None
    coordinated: CoordinatedView | None
    channels: ChannelsView | None
    directions: DirectionsView | None
    lineage: LineageView | None
    forecasts: tuple[Forecast, ...] | None
    # Files that exist but cannot be read, each with its reason.
    problems: tuple[str, ...]

    @property
    def law(self) -> LawRecord:
        return self.collected.law

    def written(self, name: str) -> bool:
        """Whether `name` (a file in `FILES`, or `FORECAST_FILE`) was written and is valid."""
        files = {
            "atlas.json": self.view,
            "coordinated.json": self.coordinated,
            "channels.json": self.channels,
            "directions.json": self.directions,
            "lineage.json": self.lineage,
            FORECAST_FILE: self.forecasts,
        }
        return files[name] is not None

    def path(self, name: str) -> str:
        """Where `name` lives, relative to the data root's parent, as the report cites it."""
        return f"data/laws/{name}" if name == FORECAST_FILE else f"data/laws/{self.slug}/{name}"

    def not_run(self, name: str) -> str:
        """Why a section has no numbers from `name`, and the command that writes it."""
        run = f"`{command(self, name)}`"
        path = f"`{self.path(name)}`"
        if any(problem.startswith(f"`{name}`") for problem in self.problems):
            return f"Not used: {path} is invalid; rerun {run}."
        return f"Not run: {path} is missing; run {run}."


def _known_laws(data_root: Path) -> dict[str, LawRecord]:
    """Every law with a completed collect run under the data root, by slug.

    Reads only each run's one-line law record, so naming a law by title stays fast.
    """
    laws: dict[str, LawRecord] = {}
    for path in sorted((data_root / "laws").glob("*/manifest.json")):
        store = StageStore(path.parent)
        manifest = store.current()
        receipts = [r for r in (manifest.stages if manifest else ()) if r.stage == "law"]
        laws.update(
            (path.parent.name, store.read_output(r, "laws.jsonl", LawRecord)[0]) for r in receipts
        )
    return laws


def resolve_slug(data_root: Path, query: str) -> str:
    """The collected law a query names: a slug, procedure number, CELEX, COM ref or title.

    Only laws already collected under `data_root` can be reported, so a title is matched
    against their titles and the common-name table, never against the whole catalog.
    """
    text = " ".join(query.split())
    if re.fullmatch(SLUG_PATTERN, text):
        return text
    try:
        parsed = parse_query(text)
    except ValueError as error:
        raise ReportError(str(error)) from error
    if parsed.kind == "procedure":
        return procedure_slug(parsed.value)
    laws = _known_laws(data_root)
    if parsed.kind == "title":
        chosen = resolve_title(
            parsed.value, ((law.procedure_id, law.title) for law in laws.values()), LAW_ALIASES
        ).chosen
        found = [procedure_slug(chosen.procedure_id)] if chosen is not None else []
    else:
        found = [
            slug
            for slug, law in laws.items()
            if parsed.value in (law.celex_final, law.celex_proposal, law.com_reference)
        ]
    if len(found) != 1:
        raise ReportError(
            f"{query!r} names no single collected law under {data_root / 'laws'}; "
            "use its procedure number, or run `make atlas LAW=...` first"
        )
    return found[0]


def _read[T: BaseModel](path: Path, model: type[T], problems: list[str]) -> T | None:
    if not path.is_file():
        return None
    try:
        return model.model_validate_json(path.read_bytes())
    except ValidationError as error:
        # Named, not guessed around: the section that needs the file says it was not used.
        problems.append(f"`{path.name}` is invalid and was not used ({error.error_count()} errors)")
        return None


class ForecastFile(BaseModel):
    """`data/laws/forecast.json`, one file for every law `influence forecast` read.

    Only the forecasts are used; the validation and the other keys it holds are ignored.
    """

    forecasts: tuple[Forecast, ...]


def read_forecasts(path: Path, problems: list[str]) -> tuple[Forecast, ...] | None:
    file = _read(path, ForecastFile, problems)
    return None if file is None else file.forecasts


def load_law(data_root: Path, slug: str) -> LawFiles:
    bundle = data_root / "laws" / slug
    try:
        collected = load_collected(bundle)
    except PipelineError as error:
        raise ReportError(
            f"{error}; run `make atlas LAW=...` (or `make collect`) for this law first"
        ) from error
    problems: list[str] = []
    forecasts = read_forecasts(data_root / "laws" / FORECAST_FILE, problems)
    return LawFiles(
        slug=slug,
        collected=collected,
        view=_read(bundle / "atlas.json", AtlasView, problems),
        coordinated=_read(bundle / "coordinated.json", CoordinatedView, problems),
        channels=_read(bundle / "channels.json", ChannelsView, problems),
        directions=_read(bundle / "directions.json", DirectionsView, problems),
        lineage=_read(bundle / "lineage.json", LineageView, problems),
        forecasts=(
            None
            if forecasts is None
            else tuple(f for f in forecasts if f.procedure_id == collected.law.procedure_id)
        ),
        problems=tuple(problems),
    )


# --- Sections ---------------------------------------------------------------------------


def _layer(row: LayerCoverage) -> str:
    count = "" if row.count is None else f" ({row.count:,})"
    return f"{row.layer} {row.status}{count}"


def coverage_section(laws: Sequence[LawFiles]) -> list[str]:
    lines = ["## Coverage", ""]
    for law in laws:
        record = law.law
        run = law.collected.manifest.run_id
        lines.append(f"- **{record.title}** ({record.procedure_id}), collect run `{run}`.")
        lines.append(f"  - Layers: {'; '.join(_layer(row) for row in record.coverage)}.")
        gaps = [f"{row.layer} ({row.reason})" for row in record.coverage if row.reason]
        lines.append(f"  - Not complete: {'; '.join(gaps) or 'none'}.")
        written = {
            "atlas.json": law.view,
            "coordinated.json": law.coordinated,
            "channels.json": law.channels,
            "directions.json": law.directions,
            "lineage.json": law.lineage,
        }
        for name, view in written.items():
            if view is None:
                lines.append(f"  - {law.not_run(name)}")
            elif view.run_id != run:
                lines.append(f"  - `{name}` was built from an older collect run `{view.run_id}`.")
        lines.extend(f"  - {problem}" for problem in law.problems)
    return [*lines, ""]


def _heading(law: LawFiles) -> str:
    return f"**{law.law.title}** ({law.law.procedure_id})"


def _ranking_line(row: RankingRow) -> str:
    return (
        f"{row.actor_name}: full wins in {of(row.full, row.assessed_asks)} assessed asks "
        f"(partial {row.partial}; {row.unknown} unknown, outside the denominator)"
    )


def ranked(view: AtlasView) -> list[RankingRow]:
    """Rows with enough assessed asks to rank, in the order the backend chose."""
    return [row for row in view.rankings if row.assessed_asks >= MIN_ASSESSED_ASKS]


def published(view: AtlasView) -> list[LinkAssessment]:
    return [link for link in view.bundle.links if link.status == "published"]


def who_section(laws: Sequence[LawFiles]) -> list[str]:
    lines = ["## WHO wins", ""]
    for law in laws:
        lines.append(f"{_heading(law)}")
        view = law.view
        if view is None:
            lines.append(f"- {law.not_run('atlas.json')}")
        else:
            rows = ranked(view)
            links = published(view)
            lines.append(
                f"- Headline: {of(len(rows), len(view.rankings))} actors with asks have at "
                f"least {MIN_ASSESSED_ASKS} assessed final-act outcomes; "
                f"{of(len(links), len(view.bundle.links))} shown links are published."
            )
            if not rows:
                lines.append(
                    f"- No actor has {MIN_ASSESSED_ASKS} or more assessed asks, so no ranking "
                    "is shown: a '1 of 1' is an anecdote, not a winner."
                )
            lines.extend(f"- {_ranking_line(row)}" for row in rows[:TOP])
            evidence = ", ".join(f"`{i}`" for i in rows[0].evidence_record_ids[:3]) if rows else ""
            lines.append(
                f"- Evidence: `data/laws/{law.slug}/atlas.json`, field `rankings`"
                + (f"; {rows[0].actor_name}: {evidence}" if evidence else "")
                + "."
            )
        lines.extend(_credits(law))
        lines.append(
            "- Limitation: wins count only outcomes traced through published links; unknown "
            "outcomes are counted apart and never as losses; a ranking holds only within the "
            "observed coverage above."
        )
        lines.append("")
    return lines


def _credits(law: LawFiles) -> list[str]:
    lineage = law.lineage
    if lineage is None:
        return [f"- {law.not_run('lineage.json')}"]
    if lineage.status == "unknown":
        return [f"- Lineage (who put wording into the final act): unknown, {lineage.reason}"]
    counts = lineage.counts
    lines = [
        f"- Lineage: {of(counts.amendments_adopting or 0, counts.amendments)} amendments put "
        f"wording of at least {MIN_ADOPTED_RUN_WORDS} words into the final act "
        f"(`data/laws/{law.slug}/lineage.json`, field `credits`)."
    ]
    for kind, label in (("mep", "Members"), ("group", "Political groups")):
        rows = [credit for credit in lineage.credits if credit.holder_kind == kind][:TOP]
        lines.extend(
            f"- {label}: {credit.name} adopted {of(credit.amendments, credit.amendments_tabled)} "
            f"amendments tabled; {credit.phrases} phrase(s), "
            f"{credit.joint_phrases} joint (shared with another holder)"
            for credit in rows
        )
    return lines


def _article_of(phrase: AdoptedPhrase) -> str:
    return phrase.final_spans[0].record_id


def what_section(laws: Sequence[LawFiles]) -> list[str]:
    lines = ["## WHAT they win", ""]
    for law in laws:
        lines.append(_heading(law))
        lineage = law.lineage
        if lineage is None:
            lines.append(f"- {law.not_run('lineage.json')}")
        elif lineage.status == "unknown":
            lines.append(f"- Adopted wording: unknown, {lineage.reason}")
        else:
            counts = lineage.counts
            changed = (
                of(counts.linked_units, counts.changed_units)
                if counts.linked_units is not None and counts.changed_units is not None
                else "not counted"
            )
            lines.append(
                f"- Headline: {changed} new words of the final act trace to a tabled amendment "
                f"({len(lineage.adopted_phrases)} adopted phrases)."
            )
            by_article = Counter(_article_of(phrase) for phrase in lineage.adopted_phrases)
            lines.extend(
                f"- `{article}`: {count} adopted phrase(s)"
                for article, count in by_article.most_common(TOP)
            )
            longest = max(
                lineage.adopted_phrases, key=lambda p: (p.words, p.phrase_id), default=None
            )
            if longest is not None:
                lines.append(f"- Longest: {_span(longest.final_spans[0])}")
        if law.channels is not None:
            committees = ", ".join(f"{k.key} {k.count}" for k in law.channels.meps.by_committee)
            lines.append(f"- Amendments by committee: {committees or 'none listed'}.")
        lines.extend(_clusters(law))
        lines.append(
            "- Limitation: shared wording is text reuse, not proof of who drafted it or why."
        )
        lines.append("")
    return lines


def _clusters(law: LawFiles) -> list[str]:
    view = law.coordinated
    if view is None:
        return [f"- {law.not_run('coordinated.json')}"]
    crossing = [cluster for cluster in view.clusters if cluster.cross_group]
    lines = [
        f"- Coordinated amendments: {of(len(crossing), len(view.clusters))} clusters of "
        f"near-identical inserted wording span political groups "
        f"(`data/laws/{law.slug}/coordinated.json`, field `clusters`)."
    ]
    if crossing:
        cluster = crossing[0]
        lines.append(
            f"- Example `{cluster.cluster_id}`: {len(cluster.members)} amendments by "
            f"{' and '.join(cluster.political_groups) or 'groups unknown'}, at least "
            f"{cluster.inserted_words} shared inserted words:"
        )
        for member in cluster.members[:2]:
            groups = "/".join(member.political_groups) or "group unknown"
            lines.append(f"  - `{member.amendment_id}` [{groups}]: {_span(member.inserted[0])}")
    return lines


def _directions(counts: DirectionCounts, whole: int) -> str:
    return ", ".join(f"{name} {of(count, whole)}" for name, count in counts.pairs() if count)


def towards_section(laws: Sequence[LawFiles]) -> list[str]:
    lines = ["## TOWARDS what", ""]
    for law in laws:
        lines.append(_heading(law))
        view = law.directions
        if view is None:
            lines.append(f"- {law.not_run('directions.json')}")
        else:
            lines.append(
                f"- Headline: of {view.amendments:,} amendments, "
                f"{_directions(view.counts, view.amendments) or 'none counted'}."
            )
            lines.extend(
                f"- {stage.stage}: {_directions(stage.counts, stage.amendments)}"
                for stage in view.by_stage
            )
            lines.extend(
                f"- {group.group}: {_directions(group.counts, group.amendments)}"
                for group in view.by_group[:TOP]
            )
            lines.append(f"- Amendments with no author of known group: {view.without_group:,}.")
            if view.actors:
                lines.extend(
                    f"- {actor.name} ({actor.published_links} published links): "
                    f"{_directions(actor.counts, actor.published_links)}"
                    for actor in view.actors[:TOP]
                )
            else:
                lines.append(f"- No actor directions ({view.actors_status}): {view.actors_reason}")
            lines.extend(
                f"- Example {example.direction}: `{example.amendment_id}` {_span(example.span)}"
                for example in view.examples[:2]
            )
            lines.append(f"- Evidence: `data/laws/{law.slug}/directions.json`.")
        lines.append(
            "- Limitation: a direction labels the edit by English cue words, not the stance of "
            "whoever tabled or asked for it; actor directions come only from published links."
        )
        lines.append("")
    return lines


def how_section(laws: Sequence[LawFiles]) -> list[str]:
    lines = ["## HOW they win", ""]
    for law in laws:
        lines.append(_heading(law))
        view = law.channels
        if view is None:
            lines.append(f"- {law.not_run('channels.json')}")
        else:
            consultation, timing = view.consultation, view.timing.feedback_vs_proposal
            meps, coalitions = view.meps, view.coalitions
            lines.append(
                f"- Headline: {of(timing.before, timing.total)} consultation feedback items "
                f"came before the Commission's proposal ({timing.reference_date or 'date unknown'}"
                f"; {timing.on_or_after} on or after, {timing.undated} undated, "
                f"{timing.unplaced} unplaced)."
            )
            lines.append(
                f"- Consultation: {consultation.feedback:,} feedback items from "
                f"{consultation.submitters:,} submitters; "
                f"{of(consultation.organisations_with_register_id, consultation.organisations)} "
                "organisations carry a Transparency Register ID."
            )
            lines.extend(
                f"- Publication {item.publication_id or 'unknown'} "
                f"({item.publication_type or 'type unknown'}): {item.feedback:,} feedback items"
                for item in consultation.by_publication
            )
            groups = ", ".join(f"{k.key} {k.count}" for k in meps.by_political_group)
            lines.append(
                f"- Tabling: {meps.amendments:,} amendments by {meps.tabling_meps:,} Members "
                f"({meps.no_known_author:,} with no known author); by group: "
                f"{groups or 'none known'}."
            )
            lines.extend(
                f"- {mep.name} ({mep.political_group or 'group unknown'}): "
                f"{mep.amendments} amendments tabled"
                for mep in meps.top_meps[:3]
            )
            lines.append(
                f"- Coalitions: {of(coalitions.cosigned_across_groups, coalitions.amendments)} "
                "amendments co-signed across groups; "
                f"{of(coalitions.cross_group_clusters, coalitions.coordinated_clusters)} "
                "coordinated clusters span groups."
            )
            lines.extend(
                f"- {row.layer.capitalize()}: {row.status.replace('_', ' ')} ({row.reason})"
                for row in view.votes_and_meetings
            )
            lines.append(f"- Evidence: `data/laws/{law.slug}/channels.json`.")
        lines.append(
            "- Limitation: these are channels associated with the law, not causes of its "
            "wording; meetings and votes are not collected."
        )
        lines.append("")
    return lines


def next_section(laws: Sequence[LawFiles]) -> list[str]:
    lines = ["## NEXT", ""]
    for law in laws:
        lines.append(_heading(law))
        forecasts = law.forecasts
        if forecasts is None:
            lines.append(
                f"- No validated forecast; reasoned scenarios only (`data/laws/{FORECAST_FILE}` "
                "is not written: run `influence forecast`)."
            )
        else:
            scored = [f for f in forecasts if f.score_type == "probability"]
            lines.append(
                f"- Headline: {of(len(scored), len(forecasts))} forecasts carry a validated "
                "probability"
                + ("." if scored else "; no validated forecast, reasoned scenarios only.")
            )
            for item in (scored or list(forecasts))[:3]:
                outlook = f"{item.score:.2f}" if item.score is not None else item.scenario
                reason = item.reasons[0] if item.reasons else "no reason recorded"
                lines.append(
                    f"- `{item.ask_id}`: {item.score_type} {outlook} ({item.model_revision}); "
                    f"{reason}"
                )
            lines.append(f"- Evidence: `data/laws/{FORECAST_FILE}`, field `forecasts`.")
        lines.append(
            "- Limitation: a forecast is published as a probability only after a rolling "
            "time-split backtest beats the base rate; otherwise it is a scenario without a number."
        )
        lines.append("")
    return lines


def ranks(values: Sequence[float]) -> list[int]:
    """Competition ranks, 1 for the largest: equal values share a rank."""
    return [1 + sum(other > value for other in values) for value in values]


def spend_section(laws: Sequence[LawFiles]) -> list[str]:
    """Wins and declared spend side by side, per law (brief p. 8), with no causal claim."""
    lines = ["## Wins and declared spend", ""]
    for law in laws:
        lines.append(_heading(law))
        if law.view is None:
            lines.extend([f"- {law.not_run('atlas.json')}", ""])
            continue
        actors: dict[str, Actor] = {a.actor_id: a for a in law.collected.actors}
        rows = ranked(law.view)
        costs = [
            actors[r.actor_id].declared_cost_eur if r.actor_id in actors else None for r in rows
        ]
        pairs = [(row, cost) for row, cost in zip(rows, costs, strict=True) if cost is not None]
        if not pairs:
            lines.append(
                f"- {of(0, len(law.view.rankings))} actors with asks have both {MIN_ASSESSED_ASKS} "
                f"or more assessed asks and a declared lobbying cost ({len(rows)} have the "
                "asks), so wins cannot be set beside spend."
            )
        else:
            win_ranks = ranks([row.full for row, _ in pairs])
            spend_ranks = ranks([cost for _, cost in pairs])
            lines.extend(
                [
                    "| Actor | Full wins | Wins rank | Declared cost (EUR) | Spend rank |",
                    "| --- | ---: | ---: | ---: | ---: |",
                ]
            )
            lines.extend(
                f"| {row.actor_name} | {of(row.full, row.assessed_asks)} | {win} | "
                f"{cost:,.0f} | {spend} |"
                for (row, cost), win, spend in zip(pairs, win_ranks, spend_ranks, strict=True)
            )
        lines.append(
            "- Limitation: declared cost is the register's self-reported annual band for all "
            "EU lobbying, not spend on this law; side by side is not cause."
        )
        lines.append("")
    return lines


# --- Links side by side -----------------------------------------------------------------


def sample[T](items: Sequence[T], count: int, seed: int) -> list[T]:
    """A seeded uniform sample without replacement: the same seed draws the same items."""
    # A reproducible draw for readers, not a secret: the seed is printed beside it.
    return random.Random(seed).sample(list(items), min(count, len(items)))  # noqa: S311


def _url(urls: dict[str, str], document_id: str) -> str:
    return urls.get(document_id, f"no URL recorded for `{document_id}`")


def _who(amendment: Amendment) -> str:
    names = ", ".join(amendment.author_names) or "authors not listed"
    return f"tabled {amendment.tabled_on or 'undated'} by {names}"


def _link_card(position: int, law: LawFiles, view: AtlasView, link: LinkAssessment) -> list[str]:
    bundle = view.bundle
    urls = {d.document_id: d.url for d in bundle.documents}
    ask = next(a for a in bundle.asks if a.ask_id == link.ask_id)
    amendment = next(a for a in bundle.amendments if a.amendment_id == link.amendment_id)
    actor = next((a.name for a in bundle.actors if a.actor_id == ask.actor_id), ask.actor_id)
    lines = [
        f"### {position}. {actor} and `{amendment.amendment_id}` ({link.tier} tier)",
        "",
        f"- Law: {law.law.title} ({law.law.procedure_id}); link `{link.link_id}`, support "
        f"score {link.support_score:.2f} (not a probability).",
        f"- **Ask**, submitted {ask.submitted_at.date() if ask.submitted_at else 'undated'}:",
        *(f"  > {_span(span)}" for span in link.ask_spans),
        f"  - Source: {_url(urls, ask.document_id)}",
        f"- **Amendment** `{amendment.amendment_id}`, {_who(amendment)}:",
        *(f"  > {_span(span)}" for span in link.amendment_spans),
        f"  - Source: {_url(urls, amendment.document_id)}",
    ]
    finals = [
        o
        for o in bundle.outcomes
        if o.stage == "final_act"
        and o.ask_id == link.ask_id
        and o.amendment_id == link.amendment_id
        and o.result in ("full", "partial")
    ]
    articles = {a.article_id: a for a in bundle.articles}
    for outcome in finals:
        article = articles.get(outcome.article_id or "")
        where = f"{article.provision}, {_url(urls, article.document_id)}" if article else "article"
        lines.append(f"- **Final act** ({outcome.result}, {where}):")
        lines.extend(f"  > {_span(span)}" for span in outcome.spans)
    if not finals:
        lines.append("- **Final act**: not traced through this amendment to the final act.")
    return [*lines, ""]


def phrase_card(
    position: int, law: LawFiles, lineage: LineageView, phrase: AdoptedPhrase
) -> list[str]:
    collected = law.collected
    urls = {d.document_id: d.url for d in collected.documents}
    articles = {a.article_id: a for a in collected.articles}
    amendments = {a.amendment_id: a for a in collected.amendments}
    span = phrase.final_spans[0]
    article = articles.get(span.record_id)
    lines = [
        f"### {position}. Adopted phrase `{phrase.phrase_id}` ({phrase.words} words), "
        "NOT a published link",
        "",
        f"- Law: {law.law.title} ({law.law.procedure_id}).",
        f"- **Final act**{f' {article.provision}' if article else ''}:",
        f"  > {_span(span)}",
        f"  - Source: {_url(urls, article.document_id) if article else 'article not in bundle'}",
    ]
    carriers = sorted(a.amendment_id for a in lineage.adoptions if phrase.phrase_id in a.phrase_ids)
    for amendment_id in carriers[:2]:
        amendment = amendments.get(amendment_id)
        if amendment is None:
            lines.append(f"- **Amendment** `{amendment_id}`: not in the collected bundle.")
            continue
        wording = " ".join(amendment.new_text.split())
        cut = "..." if len(wording) > WORDING_CHARACTERS else ""
        lines.extend(
            [
                f"- **Amendment** `{amendment_id}`, {_who(amendment)}; its new wording:",
                f'  > "{wording[:WORDING_CHARACTERS]}{cut}"',
                f"  - Source: {_url(urls, amendment.document_id)}",
            ]
        )
    if not carriers:
        lines.append("- **Amendment**: no carrying amendment listed.")
    return [*lines, ""]


def links_section(laws: Sequence[LawFiles], count: int, seed: int) -> list[str]:
    """The jury's check: `count` published links drawn at random, quoted side by side."""
    lines = [
        "## Links side by side",
        "",
        f"A uniform random sample (seed {seed}) of published links; rerun "
        f"`influence report <law> --links {count} --seed {seed}` to draw the same ones.",
        "",
    ]
    pool = [
        (law, law.view, link)
        for law in laws
        if law.view is not None
        for link in sorted(published(law.view), key=lambda item: item.link_id)
    ]
    with_view = sum(law.view is not None for law in laws)
    if pool:
        lines.append(f"Drawn {of(min(count, len(pool)), len(pool))} published links.")
        lines.append("")
        for position, (law, view, link) in enumerate(sample(pool, count, seed), start=1):
            lines.extend(_link_card(position, law, view, link))
        return lines
    lines.append(f"0 published links across {of(with_view, len(laws))} laws with an atlas view.")
    phrases = [
        (law, law.lineage, phrase)
        for law in laws
        if law.lineage is not None
        for phrase in law.lineage.adopted_phrases
    ]
    if not phrases:
        return [*lines, "No lineage adopted phrase to show instead.", ""]
    lines.extend(
        [
            "",
            f"Instead, and **not published links**: {of(min(count, len(phrases)), len(phrases))} "
            "verbatim adoptions from `lineage.json`, amendment wording that stands in the final "
            "act. They show where wording came into the law, not who asked for it.",
            "",
        ]
    )
    for position, (law, lineage, phrase) in enumerate(sample(phrases, count, seed), start=1):
        lines.extend(phrase_card(position, law, lineage, phrase))
    return lines


def methods_section(laws: Sequence[LawFiles]) -> list[str]:
    publishable = " and ".join(sorted(assessment.DEFAULT_PUBLISHABLE))
    lines = [
        "## Methods and limits",
        "",
        "Provisional thresholds, chosen on 3 October and not calibrated on these laws:",
        "",
        f"- Links: lexical rules `{assessment.METHOD_REVISION}`; only {publishable}-tier "
        f"links are published (copied threshold {assessment.COPIED_THRESHOLD}).",
        f"- Rankings: at least {MIN_ASSESSED_ASKS} assessed asks; full wins over assessed asks.",
        f"- Coordinated amendments: at least {coordinated.MIN_INSERTED_WORDS} inserted words, "
        f"similarity {coordinated.SIMILARITY_THRESHOLD} over {coordinated.SHINGLE_WORDS}-word "
        "shingles.",
        f"- Lineage: verbatim runs of at least {MIN_ADOPTED_RUN_WORDS} words holding rare words.",
        "",
        "Cut from this version:",
        "",
        *(f"- {item}" for item in CUT),
        "",
        "Limitations the pipeline recorded:",
        "",
    ]
    seen = dict.fromkeys(
        note for law in laws if law.view is not None for note in law.view.limitations
    )
    lines.extend(f"- {note}" for note in seen)
    lines.extend(
        [
            "- Public documents only; Council and trilogue texts are opaque; identity "
            "resolution can err.",
            "- Named organisations were not contacted. Matching tabled wording is text reuse, "
            "not proof of influence.",
            "",
        ]
    )
    return lines


@dataclass(frozen=True)
class Report:
    markdown: str
    # The lines the command prints: each section's headline and the link sample.
    headlines: tuple[str, ...]
    links: tuple[str, ...]


def build_report(
    laws: Sequence[LawFiles], *, generated_at: datetime, links: int, seed: int
) -> Report:
    if not laws:
        raise ReportError("Name at least one law")
    title = laws[0].law.title if len(laws) == 1 else f"{len(laws)} EU laws"
    sample_lines = links_section(laws, links, seed)
    sections = (
        coverage_section(laws),
        who_section(laws),
        what_section(laws),
        towards_section(laws),
        how_section(laws),
        next_section(laws),
        spend_section(laws),
        sample_lines,
        methods_section(laws),
    )
    lines = [
        f"# The Influence Atlas: who shaped {title}",
        "",
        f"Generated by `influence report` on {generated_at.isoformat(timespec='seconds')} from "
        "the files under `data/laws/`. Every number is a count from those files; do not edit "
        "by hand, rerun the command.",
        "",
        *(line for section in sections for line in section),
    ]
    headlines = tuple(_headlines(sections))
    return Report("\n".join(lines).rstrip("\n") + "\n", headlines, tuple(sample_lines))


def _headlines(sections: Iterable[list[str]]) -> Iterable[str]:
    for section in sections:
        yield section[0].removeprefix("## ")
        yield from (f"  {line.removeprefix('- ')}" for line in section if "Headline:" in line)


# --- The five questions as data --------------------------------------------------------

type Section = Callable[[Sequence[LawFiles]], list[str]]
# Each question, its section builder and the files it reads, the one it needs most first.
QUESTIONS: tuple[tuple[Question, Section, tuple[str, ...]], ...] = (
    ("WHO", who_section, ("atlas.json", "lineage.json")),
    ("WHAT", what_section, ("lineage.json", "coordinated.json")),
    ("TOWARDS", towards_section, ("directions.json",)),
    ("HOW", how_section, ("channels.json",)),
    ("NEXT", next_section, (FORECAST_FILE,)),
)
EVIDENCE = re.compile(r"`(data/laws/[^`]+?\.json)`(?:, field `([^`]+)`)?")


def command(law: LawFiles, name: str) -> str:
    """The make target that writes `name` for this law."""
    target = "forecast" if name == FORECAST_FILE else dict(FILES)[name]
    return f"make {target} LAW='{law.law.procedure_id}'"


def finding(law: LawFiles, question: Question, section: Section, inputs: Sequence[str]) -> Finding:
    """One question's report lines for one law, split into headline, details and evidence.

    The lines are exactly the report's, so the explorer and `report.md` never disagree.
    """
    lines = section([law])
    # After the section title, a blank line and the law's name: bullets, some nested.
    items = [line.strip().removeprefix("- ") for line in lines[3:] if line.strip()]
    headline = next((i[len("Headline: ") :] for i in items if i.startswith("Headline: ")), None)
    limitation = next(i[len("Limitation: ") :] for i in items if i.startswith("Limitation: "))
    notes = tuple(i for i in items if i.startswith(("Not run: ", "Not used: ")))
    details = tuple(
        i
        for i in items
        if i not in notes and not i.startswith(("Headline: ", "Limitation: ", "Evidence: "))
    )
    computed = any(law.written(name) for name in inputs)
    if computed and headline is None and details:
        headline, details = details[0], details[1:]
    references = dict.fromkeys(
        EvidenceRef(file=match[1], field=match[2] or None)
        for item in items
        if item not in notes
        for match in EVIDENCE.finditer(item)
    )
    # Every written input is evidence, even when no line of the section names its field.
    cited = {reference.file for reference in references}
    references.update(
        dict.fromkeys(
            EvidenceRef(file=path, field=None)
            for name in inputs
            if law.written(name) and (path := law.path(name)) not in cited
        )
    )
    return Finding(
        question=question,
        title=lines[0].removeprefix("## "),
        status="computed" if computed else "not_run",
        headline=headline if computed else None,
        details=details if computed else (),
        evidence=tuple(references) if computed else (),
        limitation=limitation,
        command=None if computed else command(law, inputs[0]),
        notes=notes or (() if computed else (law.not_run(inputs[0]),)),
    )


def law_findings(law: LawFiles) -> LawFindings:
    """The five questions of the brief for one law, as the explorer's Outcomes tab shows them."""
    return LawFindings(
        procedure_id=law.law.procedure_id,
        slug=law.slug,
        title=law.law.title,
        run_id=law.collected.manifest.run_id,
        findings=tuple(
            finding(law, question, section, inputs) for question, section, inputs in QUESTIONS
        ),
    )


def write_report(report: Report, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(path, report.markdown.encode("utf-8"))
    return path
