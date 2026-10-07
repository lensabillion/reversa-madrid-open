"""Collected records shared by lineage CLI and dated group regressions."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from test_collect import committee_record, make_world, mep_record, scripted_cli, write_dump

from influence.schemas.atlas import Actor, Amendment

AI_ACT = "2021/0106(COD)"

SLUG = "2021-0106-COD"

LATER = datetime(2026, 10, 3, 15, 30, tzinfo=UTC)

WORDS = tuple(f"word{number}" for number in range(30))

DRAFT = " ".join(WORDS)

BASE = "Providers shall keep the logs."


def variant(*, first: int = 0, last: int = 0) -> str:
    """The draft with its first and last words replaced, each costing that many runs."""
    return " ".join(
        (
            *(f"head{n}" for n in range(first)),
            *WORDS[first : 30 - last],
            *(f"tail{n}" for n in range(last)),
        )
    )


def amendment(
    name: str,
    inserted: str = DRAFT,
    *,
    authors: tuple[int, ...] = (),
    old: str | None = BASE,
    tabled: date | None = date(2022, 3, 1),
    committee: str = "ENVI",
) -> Amendment:
    return Amendment(
        amendment_id=f"am:{SLUG}:{committee}:{name}",
        procedure_id=AI_ACT,
        document_id="doc:parltrack:ep_amendments",
        stage="committee",
        committee=committee,
        author_ids=tuple(f"actor:mep:{author}" for author in authors),
        author_names=tuple(f"Member {author}" for author in authors),
        tabled_on=tabled,
        target_provision="Article 12",
        old_text=old,
        new_text=f"{BASE} {inserted}" if inserted else "",
    )


def mep(mep_id: int, group: str | None) -> Actor:
    return Actor(
        actor_id=f"actor:mep:{mep_id}",
        kind="mep",
        name=f"Member {mep_id}",
        mep_id=mep_id,
        political_group=group,
        resolution="mep_id",
    )


def lineage_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`test_collect`'s world with the draft tabled by a PPE and an S&D Member."""
    world = make_world(tmp_path)
    write_dump(
        world.inputs.committee_amendments,
        [
            committee_record(id="PE7-1", seq=1, old=[BASE], new=[f"{BASE} {DRAFT}"], meps=[1]),
            committee_record(
                id="PE7-2",
                seq=2,
                committee=["ITRE"],
                date="2022-03-31T00:00:00",
                old=[BASE],
                new=[f"{BASE} {variant(last=1)}"],
                meps=[2],
            ),
            committee_record(id="PE7-3", seq=3),
        ],
    )
    conservative = {
        **mep_record(1, "Axel EXAMPLE"),
        "Groups": [{"groupid": "PPE", "start": "2019-07-02T00:00:00", "end": "9999-12-31"}],
    }
    benifei = {
        **mep_record(2, "Brando BENIFEI"),
        # The S&D spell covering the tabling day, which the shared record leaves out.
        "Groups": [
            {"groupid": "S&D", "start": "2019-07-02T00:00:00", "end": "2024-07-15T00:00:00"}
        ],
    }
    write_dump(world.inputs.meps, [conservative, benifei])
    scripted_cli(monkeypatch, world)
