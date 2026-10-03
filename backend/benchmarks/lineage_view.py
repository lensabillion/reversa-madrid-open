"""Feed the existing explorer (`/atlas`) with lineage instead of part 3's BM25 verdicts.

Two kinds of link, both from a consultation passage's ask to an amendment whose inserted
wording reached the final act (`lineage.adopt`):

* verbatim (`origin.find_origins`): the passage repeats 12+ words of that wording; published
  when the passage is dated before the amendment and the run is not a citation;
* reworded (`benchmarks/lineage_jev.py`): Jev answered that the passage asks for the
  amendment's change (`same_legal_change` and `actual_request` >= `JEV_THRESHOLD`, and
  neither `incompatible_legal_change` nor `shared_background`); always `unconfirmed`, because
  no publication threshold for Jev on real prose has been audited.

Everything after the links (outcomes, bundle, graph, rankings) is the pipeline's own code:
`build_view` runs with its candidate search and verdicts replaced by these links, so the
explorer needs no change. The file it writes is the same `atlas.json` that
`GET /api/v1/atlas/{slug}` serves.

From backend: uv run --locked python benchmarks/lineage_view.py --law ../data/laws/2021-0106-COD
"""

import argparse
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from unittest.mock import patch

from influence.schemas.atlas import (
    Amendment,
    Ask,
    LinkAssessment,
    Passage,
    SourceSpan,
    id_part,
)
from influence.services import pipeline
from influence.services.lineage import adopt
from influence.services.origin import find_origins, submitters_from
from influence.services.prose_match import words_of

JEV_THRESHOLD = 0.5
METHOD_REVISION = "lineage-view-1"
type Eligibility = Literal["ask_first", "amendment_first", "unknown_date"]


def amendment_span(amendment: Amendment, run: list[str]) -> SourceSpan | None:
    """Where the run's folded words stand in the amendment's new text, quoted exactly."""
    words = words_of(amendment.new_text)
    folded = [word.text for word in words]
    for first in range(len(folded) - len(run) + 1):
        if folded[first : first + len(run)] == run:
            start, end = words[first].start, words[first + len(run) - 1].end
            return SourceSpan(
                record_id=amendment.amendment_id,
                field="new_text",
                start=start,
                end=end,
                text=amendment.new_text[start:end],
            )
    return None


def eligibility(ask: Ask, amendment: Amendment) -> Eligibility:
    if ask.submitted_at is None or amendment.tabled_on is None:
        return "unknown_date"
    return "ask_first" if ask.submitted_at.date() < amendment.tabled_on else "amendment_first"


def whole(amendment: Amendment) -> SourceSpan:
    return SourceSpan(
        record_id=amendment.amendment_id,
        field="new_text",
        start=0,
        end=len(amendment.new_text),
        text=amendment.new_text,
    )


def jev_links(
    rows: Iterable[dict[str, object]],
    asks: dict[str, Ask],
    amendments: dict[str, Amendment],
    procedure_id: str,
) -> list[LinkAssessment]:
    links: list[LinkAssessment] = []
    for row in rows:
        answers = row.get("answers")
        if not isinstance(answers, dict) or not answers:
            continue
        chance = {str(key): float(value) for key, value in answers.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        if not (
            chance.get("same_legal_change", 0) >= JEV_THRESHOLD
            and chance.get("actual_request", 0) >= JEV_THRESHOLD
            and chance.get("incompatible_legal_change", 1) < JEV_THRESHOLD
            and chance.get("shared_background", 1) < JEV_THRESHOLD
        ):
            continue
        ask = asks[str(row["ask_id"])]
        amendment = amendments[str(row["amendment_id"])]
        links.append(
            LinkAssessment(
                link_id=f"link:{id_part(ask.ask_id)}:{id_part(amendment.amendment_id)}",
                procedure_id=procedure_id,
                amendment_id=amendment.amendment_id,
                ask_id=ask.ask_id,
                status="unconfirmed",
                tier="reworded",
                support_score=chance["same_legal_change"],
                signals={f"jev_{key}": value for key, value in chance.items()},
                amendment_spans=(whole(amendment),),
                ask_spans=(ask.span,),
                time_eligibility=eligibility(ask, amendment),
                method="lineage-jev-reworded",
                method_revision=METHOD_REVISION,
                limitations=(
                    "Jev's answers are support signals, not calibrated probabilities; no "
                    "publication threshold for real consultation prose has been audited.",
                ),
            )
        )
    return links


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--law", type=Path, required=True, help="data/laws/<slug> bundle")
    args = parser.parse_args()

    collected = pipeline.load_collected(args.law)
    adoption = adopt(collected)
    texts = {t.document_id: t for t in collected.document_texts}
    submissions = [
        (document, texts[document.document_id])
        for document in collected.documents
        if document.source_kind in ("hys_feedback", "hys_attachment")
        and document.document_id in texts
    ]
    amendments = {a.amendment_id: a for a in collected.amendments}
    origins = find_origins(
        adoption.phrases,
        adoption.adoptions,
        submissions,
        amendments=amendments,
        submitters=submitters_from(collected.passages, collected.actors),
        proposal_texts=[a.text for a in collected.articles if a.stage == "proposal"],
    )
    asks = {ask.ask_id: ask for ask in pipeline.asks_from_passages(collected.passages)}
    passages_by_document: dict[str, list[Passage]] = {}
    for passage in collected.passages:
        passages_by_document.setdefault(passage.document_id, []).append(passage)

    links: dict[str, LinkAssessment] = {}
    unplaced = 0
    for origin in origins:
        passage = next(
            (
                p
                for p in passages_by_document.get(origin.document_id, ())
                if p.span.start <= origin.span.start and origin.span.end <= p.span.end
            ),
            None,
        )
        if passage is None:
            unplaced += 1
            continue
        ask = asks[f"ask:{id_part(passage.passage_id)}"]
        run = [word.text for word in words_of(origin.span.text)]
        for amendment_id in origin.amendment_ids:
            amendment = amendments[amendment_id]
            span = amendment_span(amendment, run)
            timing: Eligibility = (
                "unknown_date"
                if origin.precedes is None
                else "ask_first"
                if origin.precedes
                else "amendment_first"
            )
            published = span is not None and timing == "ask_first" and not origin.is_citation
            link_id = f"link:{id_part(ask.ask_id)}:{id_part(amendment_id)}"
            links[link_id] = LinkAssessment(
                link_id=link_id,
                procedure_id=collected.law.procedure_id,
                amendment_id=amendment_id,
                ask_id=ask.ask_id,
                status="published" if published else "unconfirmed",
                tier="copied",
                support_score=1.0,
                signals={"shared_words": float(origin.words)},
                amendment_spans=() if span is None else (span,),
                ask_spans=(origin.span,),
                time_eligibility=timing,
                method="lineage-verbatim-origin",
                method_revision=METHOD_REVISION,
            )
    verbatim = len(links)

    jev_path = args.law / "lineage-jev.json"
    rows: list[dict[str, object]] = json.loads(jev_path.read_text()) if jev_path.is_file() else []
    for link in jev_links(rows, asks, amendments, collected.law.procedure_id):
        links.setdefault(link.link_id, link)
    reworded = len(links) - verbatim

    shown = tuple(links.values())
    with (
        patch.object(pipeline, "find_candidates", return_value=()),
        patch.object(pipeline, "assess_candidates", return_value=shown),
    ):
        view = pipeline.build_view(collected, generated_at=datetime.now(UTC))
    view = view.model_copy(
        update={
            "ask_method": "lineage-v0",
            "limitations": (
                "Links come from lineage: amendments whose inserted wording (12+ identical "
                "words absent from the proposal) stands in the final act, linked to the "
                "consultation passages that repeat that wording (verbatim) or that Jev judged "
                "to ask for the same change (reworded, always unconfirmed). Shared wording "
                "or meaning is not proof of authorship.",
                f"Lineage: {len(adoption.phrases)} adopted phrases in "
                f"{len(adoption.adoptions)} amendments; {verbatim} verbatim link(s) from "
                f"{len(origins)} origin match(es) in {len(submissions)} submissions "
                f"({unplaced} not inside a passage); {reworded} reworded link(s) from "
                f"{len(rows)} Jev row(s).",
                *adoption.limitations,
                *view.limitations[2:],
            ),
        }
    )
    path = pipeline.write_view(view, args.law)
    print(
        f"{verbatim} verbatim and {reworded} reworded links "
        f"({sum(link.status == 'published' for link in shown)} published); wrote {path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
