"""The shared collection contracts: every rule that keeps unknowns, evidence and IDs honest."""

import json
from datetime import UTC, datetime

import pytest
from collection_fixture import (
    AM1_NEW,
    FIXTURE_DIRECTORY,
    build_fixture,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from influence.schemas.atlas import (
    ATLAS_SCHEMA_VERSION,
    Actor,
    Amendment,
    AtlasRecord,
    LawRecord,
    LayerCoverage,
    RunManifest,
    SourceSpan,
    document_id,
    id_part,
    mep_actor_id,
    named_actor_id,
    register_actor_id,
    span_matches,
)

PROPERTY = settings(derandomize=True, database=None, deadline=None)
FIXTURE = build_fixture()
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def changed[T: AtlasRecord](record: T, **updates: object) -> T:
    """Revalidate a fixture record with some fields replaced."""
    return type(record).model_validate({**record.model_dump(), **updates})


# --- The committed files ----------------------------------------------------------------


def test_every_fixture_line_validates_and_carries_the_schema_version() -> None:
    for stem, records in FIXTURE.tables().items():
        lines = (FIXTURE_DIRECTORY / f"{stem}.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == len(records) > 0, stem
        for line, record in zip(lines, records, strict=True):
            assert type(record).model_validate_json(line) == record
            assert json.loads(line)["schema_version"] == ATLAS_SCHEMA_VERSION


# --- Evidence and joins -----------------------------------------------------------------


# --- Identifiers ------------------------------------------------------------------------


def test_identifier_builders() -> None:
    assert document_id("hys_feedback", "2665480") == "doc:hys_feedback:2665480"
    assert document_id("cellar", "celex/32024R1689 (EN)") == "doc:cellar:celex-32024R1689-EN"
    assert register_actor_id("880143435725-46") == "actor:tr:880143435725-46"
    assert mep_actor_id(124831) == "actor:mep:124831"
    assert named_actor_id("hys_feedback", "acme corp") == "actor:name:hys_feedback.acme-corp"
    with pytest.raises(ValueError, match="No usable identifier"):
        id_part(" /() ")


@PROPERTY
@given(st.text(min_size=1))
def test_id_part_is_safe_or_refuses(value: str) -> None:
    try:
        part = id_part(value)
    except ValueError:
        return
    assert part
    assert all(
        character.isascii() and (character.isalnum() or character in "._-") for character in part
    )
    assert id_part(part) == part


@pytest.mark.parametrize("procedure", ["2021/106(COD)", "2021-0106-COD", "2021/0106", ""])
def test_procedure_id_must_be_a_full_reference(procedure: str) -> None:
    with pytest.raises(ValidationError):
        changed(FIXTURE.laws[0], procedure_id=procedure)


def test_extra_fields_and_mutation_are_rejected() -> None:
    with pytest.raises(ValidationError):
        changed(FIXTURE.laws[0], unexpected=1)
    with pytest.raises(ValidationError):
        FIXTURE.laws[0].title = "changed"  # type: ignore[misc]  # pyright: ignore[reportAttributeAccessIssue]


# --- Validators -------------------------------------------------------------------------


def test_span_length_must_match_its_text() -> None:
    with pytest.raises(ValidationError, match="code points"):
        SourceSpan(record_id="doc:cellar:x", start=0, end=4, text="abc")


def test_span_offsets_count_code_points_not_utf16_units() -> None:
    source = "\U0001d54f shall 'may'"
    span = SourceSpan(record_id="doc:cellar:x", start=8, end=13, text="'may'")
    assert span_matches(span, source)
    assert not span_matches(span, source.replace("may", "can"))


@PROPERTY
@given(st.text(min_size=1, max_size=40), st.text(max_size=20), st.text(max_size=20))
def test_span_built_from_any_text_matches_only_that_text(
    quote: str, before: str, after: str
) -> None:
    span = SourceSpan(
        record_id="doc:cellar:x", start=len(before), end=len(before) + len(quote), text=quote
    )
    assert span_matches(span, before + quote + after)


def test_coverage_gap_needs_a_reason_and_complete_does_not() -> None:
    assert LayerCoverage(layer="asks", status="complete", count=0).reason is None
    with pytest.raises(ValidationError, match="must say why"):
        LayerCoverage(layer="asks", status="missing")


def test_law_lists_each_layer_once() -> None:
    law = FIXTURE.laws[0]
    with pytest.raises(ValidationError, match="more than once"):
        LawRecord.model_validate({**law.model_dump(), "coverage": [*law.coverage, law.coverage[0]]})


def test_amendment_keeps_unknown_original_apart_from_an_insertion() -> None:
    amendment = FIXTURE.amendments[0]
    assert changed(amendment, old_text=None).old_text is None
    assert changed(amendment, old_text="").old_text == ""
    assert changed(amendment, new_text="").new_text == ""
    with pytest.raises(ValidationError, match="original or proposed"):
        Amendment.model_validate({**amendment.model_dump(), "old_text": None, "new_text": " "})


def test_actor_identity_must_match_how_it_was_resolved() -> None:
    organisation = FIXTURE.actors[0]
    with pytest.raises(ValidationError, match="register ID"):
        changed(organisation, register_id=None)
    mep = next(item for item in FIXTURE.actors if item.kind == "mep")
    with pytest.raises(ValidationError, match="MEP ID"):
        changed(mep, mep_id=None)
    ambiguous = next(item for item in FIXTURE.actors if item.resolution == "ambiguous")
    with pytest.raises(ValidationError, match="candidates"):
        Actor.model_validate({**ambiguous.model_dump(), "candidate_ids": []})


def test_run_is_complete_only_with_a_law_an_end_time_and_no_failed_stage() -> None:
    complete, running = FIXTURE.manifests
    assert running.completed_at is None
    with pytest.raises(ValidationError, match="completion time"):
        changed(complete, completed_at=None)
    with pytest.raises(ValidationError, match="completion time"):
        changed(complete, procedure_id=None)
    failed = complete.stages[0].model_copy(update={"status": "failed"})
    with pytest.raises(ValidationError, match="failed stage"):
        RunManifest.model_validate({**complete.model_dump(), "stages": [failed]})
    assert changed(running, status="failed", completed_at=NOW).status == "failed"


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValidationError):
        changed(FIXTURE.documents[0], retrieved_at=datetime(2026, 10, 3, 12, 0))


def test_amendment_text_constant_is_the_fixture_amendment() -> None:
    assert FIXTURE.amendments[0].new_text == AM1_NEW
