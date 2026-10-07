"""Record files and stage receipts: reuse only intact work, publish only verified runs."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from collection_fixture import build_fixture

from influence.extraction.records import (
    MANIFEST_NAME,
    RecordError,
    StageStore,
    encode_records,
    input_hash,
    read_records,
)
from influence.schemas.atlas import (
    Amendment,
    DocumentText,
    LawRecord,
    RunManifest,
    StageReceipt,
    StageStatus,
)

FIXTURE = build_fixture()
STARTED = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
INPUTS = input_hash("2099/0001(COD)", "revision-1")


def saved(
    store: StageStore,
    status: StageStatus = "partial",
    errors: tuple[str, ...] = ("1 attachment failed",),
) -> StageReceipt:
    return store.save(
        "collect",
        INPUTS,
        {"amendments.jsonl": FIXTURE.amendments, "laws.jsonl": FIXTURE.laws},
        status=status,
        seconds=1.25,
        counts={"amendments": 3},
        errors=errors,
    )


def manifest(*stages: StageReceipt) -> RunManifest:
    return RunManifest(
        run_id="run:2099-0001-COD:20261003T120000Z",
        query="2099/0001(COD)",
        procedure_id="2099/0001(COD)",
        status="complete",
        started_at=STARTED,
        completed_at=STARTED,
        code_revision="revision-1",
        stages=stages,
    )


def test_records_round_trip(tmp_path: Path) -> None:
    content, count = encode_records(FIXTURE.amendments)
    path = tmp_path / "amendments.jsonl"
    path.write_bytes(content)
    assert count == 3
    assert tuple(read_records(path, Amendment)) == FIXTURE.amendments


def test_reading_names_the_bad_line_and_a_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "amendments.jsonl"
    content, _ = encode_records(FIXTURE.amendments[:1])
    path.write_bytes(content + b'{"amendment_id": 1}\n')
    with pytest.raises(RecordError, match="line 2 is invalid"):
        tuple(read_records(path, Amendment))
    with pytest.raises(RecordError, match="Cannot read"):
        tuple(read_records(tmp_path / "absent.jsonl", Amendment))


def test_input_hash_separates_its_parts() -> None:
    assert input_hash("ab", "c") != input_hash("a", "bc")
    assert input_hash("a", "b") == input_hash("a", "b")
    assert len(input_hash()) == 64


def test_save_writes_files_and_a_receipt_with_relative_paths(tmp_path: Path) -> None:
    store = StageStore(tmp_path)
    receipt = saved(store)
    assert receipt.status == "partial"
    assert receipt.counts == {"amendments": 3}
    assert receipt.errors == ("1 attachment failed",)
    assert [output.path for output in receipt.outputs] == [
        f"stages/collect/{INPUTS}/amendments.jsonl",
        f"stages/collect/{INPUTS}/laws.jsonl",
    ]
    assert [output.records for output in receipt.outputs] == [3, 2]
    assert store.read_output(receipt, "laws.jsonl", LawRecord) == FIXTURE.laws
    with pytest.raises(RecordError, match="no output named"):
        store.read_output(receipt, "absent.jsonl", LawRecord)


@pytest.mark.parametrize(
    ("status", "errors"),
    [("partial", ("CELLAR did not answer",)), ("partial", ()), ("complete", ("1 failed",))],
)
def test_load_never_reuses_a_stage_saved_partial_or_with_errors(
    tmp_path: Path, status: StageStatus, errors: tuple[str, ...]
) -> None:
    # A gap caused by one bad run (a source down) must not outlive it: rerun the stage.
    store = StageStore(tmp_path)
    saved(store, status, errors)
    assert store.load("collect", INPUTS) is None


def test_load_reuses_only_an_intact_stage(tmp_path: Path) -> None:
    store = StageStore(tmp_path)
    assert store.load("collect", INPUTS) is None
    receipt = saved(store, "complete", ())
    reused = store.load("collect", INPUTS)
    assert reused is not None
    assert reused.status == "reused"
    assert reused.outputs == receipt.outputs
    assert store.load("collect", input_hash("other")) is None
    store.output_path(receipt.outputs[0]).write_text("tampered", encoding="utf-8")
    assert store.load("collect", INPUTS) is None


def test_load_ignores_a_corrupt_receipt_and_a_deleted_output(tmp_path: Path) -> None:
    store = StageStore(tmp_path)
    receipt = saved(store, "complete", ())
    assert store.load("collect", INPUTS) is not None
    store.output_path(receipt.outputs[1]).unlink()
    assert store.load("collect", INPUTS) is None
    (store.stage_directory("collect", INPUTS) / "receipt.json").write_text("{", encoding="utf-8")
    assert store.load("collect", INPUTS) is None


def test_publish_writes_the_manifest_only_when_outputs_verify(tmp_path: Path) -> None:
    store = StageStore(tmp_path)
    assert store.current() is None
    receipt = saved(store)
    run = manifest(receipt)
    path = store.publish(run)
    assert path == tmp_path / MANIFEST_NAME
    assert store.current() == run
    assert (tmp_path / "runs" / "run-2099-0001-COD-20261003T120000Z.json").exists()

    store.output_path(receipt.outputs[0]).write_text("tampered", encoding="utf-8")
    later = run.model_copy(update={"run_id": "run:later"})
    with pytest.raises(RecordError, match="no longer matches"):
        store.publish(later)
    assert store.current() == run


def test_current_rejects_an_invalid_manifest(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_NAME).write_text("{}", encoding="utf-8")
    with pytest.raises(RecordError, match="is invalid"):
        StageStore(tmp_path).current()


SEPARATORS = (
    "\N{LINE SEPARATOR}",
    "\N{PARAGRAPH SEPARATOR}",
    "\N{NEXT LINE}",
    "\N{LINE TABULATION}",
    "\N{FORM FEED}",
    "\N{INFORMATION SEPARATOR TWO}",
)


@pytest.mark.parametrize("separator", SEPARATORS)
def test_a_text_holding_a_unicode_line_separator_survives_a_round_trip(
    tmp_path: Path, separator: str
) -> None:
    """Real submissions hold U+2028; splitlines() cut such a record in half (AI Act run)."""
    record = DocumentText(document_id="doc:hys_feedback:1", text=f"before{separator}after")
    body, count = encode_records([record])
    path = tmp_path / "document_texts.jsonl"
    path.write_bytes(body)
    assert count == 1
    assert list(read_records(path, DocumentText)) == [record]


def test_an_empty_file_has_no_records_and_a_blank_line_is_still_an_error(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    assert list(read_records(path, DocumentText)) == []
    body, _ = encode_records([DocumentText(document_id="doc:hys_feedback:1", text="x")])
    path.write_bytes(body + b"\n" + body)
    with pytest.raises(RecordError, match="line 2 is invalid"):
        list(read_records(path, DocumentText))


def test_a_file_without_a_final_line_feed_is_still_read_whole(tmp_path: Path) -> None:
    record = DocumentText(document_id="doc:hys_feedback:1", text="no trailing newline")
    body, _ = encode_records([record])
    path = tmp_path / "document_texts.jsonl"
    path.write_bytes(body.rstrip(b"\n"))
    assert list(read_records(path, DocumentText)) == [record]
