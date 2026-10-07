"""Collection records read back for lineage, and the matching public-source test world."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_collect import FEEDBACK, World, make_world
from test_collect import LATER as OTHER_LAW
from test_collect import RECENT as RECENT_DAY
from test_hys import Json, as_json, feedback, feedback_page
from test_parltrack import Record, committee_record, mep_record, write_dump

from influence.extraction.records import StageStore
from influence.repositories import hys
from influence.schemas.atlas import Actor
from influence.services import collected as collection_records
from influence.services.collected import PipelineError

AI_ACT = "2021/0106(COD)"
SLUG = "2021-0106-COD"
RARE = "for at least six months after the system is placed on the market"
LATER = datetime(2026, 10, 3, 12, 30, tzinfo=UTC)


def matching_world(
    tmp_path: Path, extra_records: Sequence[Record] = (), extra_feedback: Sequence[Json] = ()
) -> World:
    world = make_world(tmp_path)
    write_dump(
        world.inputs.committee_amendments,
        [
            committee_record(),
            committee_record(
                id="PE7-7",
                seq=7,
                old=["Providers shall keep the logs."],
                new=[f"Providers shall keep the logs {RARE}."],
            ),
            # Another law's recent amendment, as in make_world: the dump reaches past the
            # AI Act's end, so its amendment layer stays complete.
            committee_record(id="PE8-8", reference=OTHER_LAW, meps=[], date=RECENT_DAY),
            *extra_records,
        ],
    )
    asking = feedback(
        4,
        feedback=f"We propose that providers keep the logs {RARE}.",
        organization="Acme Unknown Lobby",
        trNumber=None,
        userType="COMPANY",
        attachments=[],
    )
    page = as_json(feedback_page([*FEEDBACK, asking, *extra_feedback], last=True))
    world.scripted.script = [
        (fragment, page if fragment == hys.feedback_url(14488, 0) else response)
        for fragment, response in world.scripted.script
    ]
    return world


def collected(world: World) -> collection_records.Collected:
    return collection_records.load_collected(world.collect().bundle)


def test_a_bundle_without_a_complete_collect_run_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="No completed collect run"):
        collection_records.load_collected(tmp_path)

    result = make_world(tmp_path).collect()
    store = StageStore(result.bundle)
    store.publish(result.manifest.model_copy(update={"stages": result.manifest.stages[:2]}))
    with pytest.raises(PipelineError, match=r"lacks stages \['asks', 'law'\]"):
        collection_records.load_collected(result.bundle)

    law = result.law
    twice = store.save("law", "f" * 64, {"laws.jsonl": (law, law)}, status="complete", seconds=0)
    stages = (*result.manifest.stages[:3], twice)
    store.publish(result.manifest.model_copy(update={"stages": stages}))
    with pytest.raises(PipelineError, match="holds 2 laws"):
        collection_records.load_collected(result.bundle)


def test_an_mep_missing_from_the_dump_still_has_an_identity(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    write_dump(world.inputs.meps, [mep_record(197721)])

    result = world.collect()

    actors = StageStore(result.bundle).read_output(result.manifest.stages[1], "actors.jsonl", Actor)
    names = {actor.actor_id: actor.name for actor in actors}
    assert names["actor:mep:125042"] == "MEP 125042 (not in the Parltrack MEP dump)"
    assert result.manifest.stages[1].counts["meps_not_in_dump"] == 1
