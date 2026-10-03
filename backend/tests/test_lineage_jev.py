"""Reworded origins in lineage: BM25 shortlists, Jev judges, semantic origins are dated.

Every test runs offline: `test_jev_judge.FakeJev` answers in place of TypeSafe.
"""

import ssl
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr
from test_coordinated import AI_ACT, coordinated_world
from test_jev_judge import SUPPORTING, FakeJev
from test_lineage_assembly import ACME, NOW, collected
from test_origin import document

from influence import cli
from influence.schemas.atlas import Actor, Passage, SourceSpan
from influence.services import jev, jev_judge, lineage_assembly, lineage_jev
from influence.services.lineage import adopt
from influence.services.lineage_jev import reworded_origins
from influence.services.pipeline import Collected

# Shares three of the adopted amendment's rare words but no run of eight: only a meaning
# judge can tie it to the amendment.
REWORDED = "We would like the rules to cover novel3, novel11 and novel17 in every case."
CITIZEN = Actor(
    actor_id="actor:citizens:1", kind="citizens", name="A citizen", resolution="unresolved"
)


def _passage(key: str, document_id: str, text: str, actor: str = ACME.actor_id) -> Passage:
    return Passage(
        passage_id=f"passage:{key}",
        procedure_id="2099/0001(COD)",
        document_id=document_id,
        actor_id=actor,
        span=SourceSpan(record_id=document_id, start=0, end=len(text), text=text),
        submitted_at=None,
    )


def _world(*extra: tuple[str, str, datetime | None, str]) -> Collected:
    """`test_lineage_assembly`'s law with one reworded paper, plus `extra` documents.

    Each extra is (key, text, published, actor id); its one passage quotes it whole.
    """
    base = collected()
    papers = [("9", REWORDED, datetime(2099, 1, 1, tzinfo=UTC), ACME.actor_id), *extra]
    documents = [document(key, text, published=published) for key, text, published, _ in papers]
    passages = [
        _passage(key, source.document_id, text, actor).model_copy(
            update={"submitted_at": published}
        )
        for (key, text, published, actor), (source, _) in zip(papers, documents, strict=True)
    ]
    return replace(
        base,
        documents=(*base.documents, *(source for source, _ in documents)),
        document_texts=(*base.document_texts, *(text for _, text in documents)),
        passages=(*base.passages, *passages),
        actors=(*base.actors, CITIZEN),
    )


def _judge(tmp_path: Path, fake: FakeJev, max_usd: float = 1.0) -> jev_judge.JevJudge:
    client = jev.JevClient(SecretStr("offline"), ssl.create_default_context(), transport=fake)
    return jev_judge.JevJudge(client=client, cache=tmp_path / "jev", max_usd=max_usd, workers=2)


def _submitters(world: Collected) -> dict[str, Actor]:
    actors = {actor.actor_id: actor for actor in world.actors}
    return {p.document_id: actors[p.actor_id] for p in world.passages if p.actor_id in actors}


def test_a_reworded_request_jev_supports_becomes_a_dated_semantic_origin(tmp_path: Path) -> None:
    world = _world()
    adoption = adopt(world)
    fake = FakeJev()

    origins, note = reworded_origins(
        world, adoption.adoptions, _judge(tmp_path, fake), submitters=_submitters(world)
    )

    (origin,) = [o for o in origins if o.document_id == "doc:hys_attachment:9"]
    (phrase,) = adoption.phrases
    assert (origin.kind, origin.phrase_id) == ("semantic", phrase.phrase_id)
    assert origin.similarity == pytest.approx(0.8)  # the weakest supporting answer
    assert origin.span.text == REWORDED
    assert origin.organisation == ACME.name
    assert origin.amendment_ids == ("am:2099-0001-COD:IMCO:1",)
    assert (origin.precedes, origin.eligibility) == (True, "ask_first")
    assert origin.counts_as_origin
    assert "cleared 0.67 on all four answers" in note
    assert any(state["submission_new"] == REWORDED for state in fake.states)


def test_a_pair_below_the_cutoff_or_not_answered_is_no_origin(tmp_path: Path) -> None:
    world = _world()
    weak = FakeJev(answer=lambda _: {**SUPPORTING, "same_legal_change": 0.5})
    origins, note = reworded_origins(
        world, adopt(world).adoptions, _judge(tmp_path / "a", weak), submitters=_submitters(world)
    )
    assert origins == ()
    assert "; 0 cleared" in note

    failing = FakeJev(fail=lambda _: True)
    origins, note = reworded_origins(
        world, adopt(world).adoptions, _judge(tmp_path / "b", failing), submitters={}
    )
    assert origins == ()
    assert "Jev judged 0 of" in note


def test_pairs_verbatim_search_found_are_not_asked_again(tmp_path: Path) -> None:
    world = _world()
    fake = FakeJev()
    known = frozenset((d.document_id, "am:2099-0001-COD:IMCO:1") for d in world.documents)
    origins, _ = reworded_origins(
        world, adopt(world).adoptions, _judge(tmp_path, fake), submitters={}, known=known
    )
    assert origins == ()
    assert fake.states == []


def test_one_origin_per_document_and_amendment_and_unknown_dates_stay_unknown(
    tmp_path: Path,
) -> None:
    world = _world(("8", REWORDED + " Again.", None, CITIZEN.actor_id))
    second = _passage("8b", "doc:hys_attachment:8", REWORDED, CITIZEN.actor_id)
    world = replace(world, passages=(*world.passages, second))

    origins, _ = reworded_origins(
        world, adopt(world).adoptions, _judge(tmp_path, FakeJev()), submitters=_submitters(world)
    )

    undated = [o for o in origins if o.document_id == "doc:hys_attachment:8"]
    assert len(undated) == 1
    (origin,) = undated
    assert origin.organisation is None  # a citizen is never named
    assert (origin.precedes, origin.eligibility) == (None, "unknown_date")
    assert not origin.counts_as_origin


def test_a_passage_without_text_is_not_asked(tmp_path: Path) -> None:
    orphan = _passage("6", "doc:hys_attachment:missing", REWORDED)
    world = _world()
    world = replace(world, passages=(*world.passages, orphan))
    fake = FakeJev()

    origins, _ = reworded_origins(
        world, adopt(world).adoptions, _judge(tmp_path, fake), submitters={}
    )

    assert {o.document_id for o in origins} == {"doc:hys_attachment:9"}
    assert len(fake.states) == 1


def test_a_pair_over_the_request_bound_is_counted_not_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # BM25 already refuses passages and amendments past 800 tokens, so no real pair reaches
    # the bound; the guard stays for a future caller with a larger context.
    def too_large(*_: object) -> None:
        return None

    monkeypatch.setattr(lineage_jev, "judge_request", too_large)
    world = _world()
    fake = FakeJev()

    origins, note = reworded_origins(
        world, adopt(world).adoptions, _judge(tmp_path, fake), submitters={}
    )

    assert origins == ()
    assert fake.states == []
    assert "over the request bound" in note


def test_the_lineage_view_adds_reworded_origins_and_says_how(tmp_path: Path) -> None:
    view = lineage_assembly.build_lineage(
        _world(), generated_at=NOW, judge=_judge(tmp_path, FakeJev())
    )
    kinds = {(o.document_id, o.kind) for o in view.origins}
    assert ("doc:hys_attachment:9", "semantic") in kinds
    assert ("doc:hys_attachment:1", "verbatim") in kinds
    assert lineage_assembly.VERBATIM_ONLY not in view.limitations
    assert lineage_assembly.REWORDED in view.limitations
    assert any(
        note.startswith("Reworded origins (jev-reworded-origins)") for note in view.limitations
    )
    plain = lineage_assembly.build_lineage(_world(), generated_at=NOW)
    assert all(o.kind == "verbatim" for o in plain.origins)
    assert lineage_assembly.VERBATIM_ONLY in plain.limitations


def test_the_lineage_command_needs_a_key_and_a_positive_budget_for_jev(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(cli.JEV_KEY_VARIABLE, raising=False)
    assert cli.main(["lineage", AI_ACT, "--data-root", str(tmp_path), "--jev"]) == 2
    assert cli.JEV_KEY_VARIABLE in capsys.readouterr().err

    monkeypatch.setenv(cli.JEV_KEY_VARIABLE, "offline")
    args = ["lineage", AI_ACT, "--data-root", str(tmp_path), "--jev", "--jev-max-usd", "0"]
    assert cli.main(args) == 2
    assert "positive amount" in capsys.readouterr().err


def test_the_lineage_command_hands_the_view_a_cached_jev_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinated_world(tmp_path, monkeypatch)
    monkeypatch.setenv(cli.JEV_KEY_VARIABLE, "offline")
    seen: list[jev_judge.JevJudge | None] = []
    real = lineage_assembly.build_lineage

    def spy(
        collected: Collected, *, generated_at: datetime, judge: jev_judge.JevJudge | None = None
    ) -> lineage_assembly.LineageView:
        seen.append(judge)
        return real(collected, generated_at=generated_at)

    monkeypatch.setattr(cli, "build_lineage", spy)
    args = ["lineage", AI_ACT, "--data-root", str(tmp_path), "--jev", "--jev-max-usd", "2"]

    assert cli.main(args) == 0
    (judge,) = seen
    assert judge is not None
    assert (judge.cache, judge.max_usd) == (tmp_path / "cache" / "jev", 2.0)


def test_a_pair_with_a_different_object_is_no_origin(tmp_path: Path) -> None:
    world = _world()
    other_object = FakeJev(same=lambda _: 0.4)

    origins, note = reworded_origins(
        world,
        adopt(world).adoptions,
        _judge(tmp_path, other_object),
        submitters=_submitters(world),
    )

    assert origins == ()
    assert other_object.second_stage  # asked only of pairs that cleared the four
    assert len(other_object.second_stage) <= len(other_object.states)
    assert "and 0 of them also on same-object-v1" in note
    assert "; 0 origin(s)." in note


def test_a_second_stage_the_budget_left_unasked_is_no_origin(tmp_path: Path) -> None:
    world = _world()
    first = FakeJev()
    judge = _judge(tmp_path, first)
    reworded_origins(world, adopt(world).adoptions, judge, submitters=_submitters(world))
    # Keep the four answers cached and forget the second stage's: with no budget left, it
    # cannot be asked again.
    for name in [p.name for p in (tmp_path / "jev").iterdir()]:
        result = jev.JevResult.model_validate_json((tmp_path / "jev" / name).read_bytes())
        if jev_judge.SAME_OBJECT in result.answers:
            (tmp_path / "jev" / name).unlink()
    broke = FakeJev()

    origins, note = reworded_origins(
        world,
        adopt(world).adoptions,
        _judge(tmp_path, broke, max_usd=0.0),
        submitters=_submitters(world),
    )

    assert origins == ()
    assert broke.states == []  # the four came from the cache
    assert broke.second_stage == []
    assert "not asked)" in note
    assert "0 not asked)" not in note
