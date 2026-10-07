"""Source identity stays separate from quote-record identity and missing provenance."""

from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_collected import LATER
from test_lineage_views import adopted_world

from influence.schemas.lineage import LineageView
from influence.services.collected import PipelineError
from influence.services.lineage_assembly import build_lineage
from influence.services.lineage_sources import attach_sources


def test_quotes_map_to_their_collected_sources_and_shared_files_are_deduplicated(
    tmp_path: Path,
) -> None:
    collected = adopted_world(tmp_path)
    view = build_lineage(collected, generated_at=LATER)
    source_by_id = {source.document_id: source for source in collected.documents}
    documents = {document.document_id: document for document in view.documents}
    records = {record.record_id: record for record in view.source_records}
    (origin,) = view.origins
    (support,) = origin.supports
    assert records[support.submission_span.record_id].document_id == origin.document_id
    amendment = next(a for a in collected.amendments if a.amendment_id == support.amendment_id)
    final = next(a for a in collected.articles if a.article_id == support.final_span.record_id)
    assert records[amendment.amendment_id].document_id == amendment.document_id
    assert records[final.article_id].document_id == final.document_id
    assert final.article_id != final.document_id
    assert records[final.article_id].label == "Article 12"
    assert records[amendment.amendment_id].label == "Amendment 7"
    assert documents[amendment.document_id].source_kind == "parltrack"
    assert len(documents) == len({record.document_id for record in records.values()})
    for document in documents.values():
        source = source_by_id[document.document_id]
        assert (document.url, document.sha256, document.retrieved_at) == (
            source.url,
            source.sha256,
            source.retrieved_at,
        )
    duplicates = replace(
        collected,
        documents=(*collected.documents, *collected.documents),
        amendments=(*collected.amendments, *collected.amendments),
        articles=(*collected.articles, *collected.articles),
    )
    assert attach_sources(view, duplicates) == view


def test_missing_source_metadata_keeps_identity_and_an_explicit_reason(tmp_path: Path) -> None:
    collected = adopted_world(tmp_path)
    view = build_lineage(collected, generated_at=LATER)
    incomplete = attach_sources(view, replace(collected, documents=()))
    assert incomplete.documents == ()
    assert incomplete.source_records
    assert {record.document_id for record in incomplete.source_records} == {
        record.document_id for record in view.source_records
    }
    assert all(record.unavailable_reason for record in incomplete.source_records)
    assert incomplete.origins == view.origins
    assert (
        next(r for r in incomplete.source_records if r.record_type == "document_text").label is None
    )
    no_numbers = replace(
        collected,
        amendments=tuple(a.model_copy(update={"number": None}) for a in collected.amendments),
    )
    amended = attach_sources(view, no_numbers)
    source = next(r for r in amended.source_records if r.record_type == "amendment")
    assert source.label == next(
        a.target_provision for a in no_numbers.amendments if a.amendment_id == source.record_id
    )


@pytest.mark.parametrize("kind", ["document", "amendment", "article"])
def test_conflicting_collected_identity_is_an_error(tmp_path: Path, kind: str) -> None:
    collected = adopted_world(tmp_path)
    view = build_lineage(collected, generated_at=LATER)
    if kind == "document":
        changed = collected.documents[0].model_copy(update={"url": "https://example.org/other"})
        collected = replace(collected, documents=(*collected.documents, changed))
    elif kind == "amendment":
        changed_amendment = collected.amendments[0].model_copy(update={"number": 999})
        collected = replace(collected, amendments=(*collected.amendments, changed_amendment))
    else:
        changed_article = collected.articles[0].model_copy(update={"provision": "Different title"})
        collected = replace(collected, articles=(*collected.articles, changed_article))
    with pytest.raises(PipelineError, match="Conflicting"):
        attach_sources(view, collected)


@pytest.mark.parametrize("kind", ["amendment", "article", "text"])
def test_missing_quoted_record_is_not_inferred_from_its_id(tmp_path: Path, kind: str) -> None:
    collected = adopted_world(tmp_path)
    view = build_lineage(collected, generated_at=LATER)
    missing = (
        replace(collected, amendments=())
        if kind == "amendment"
        else replace(collected, articles=())
        if kind == "article"
        else replace(collected, document_texts=())
    )
    with pytest.raises(PipelineError, match="Missing quoted"):
        attach_sources(view, missing)


@pytest.mark.parametrize(
    "corruption",
    [
        "duplicate_document",
        "duplicate_record",
        "missing_record",
        "wrong_kind",
        "missing_metadata",
        "reason_with_metadata",
        "unused_document",
    ],
)
def test_view_rejects_inconsistent_source_mappings(tmp_path: Path, corruption: str) -> None:
    collected = adopted_world(tmp_path)
    view = build_lineage(collected, generated_at=LATER)
    documents, records = view.documents, view.source_records
    if corruption == "duplicate_document":
        documents = (*documents, documents[0])
    elif corruption == "duplicate_record":
        records = (*records, records[0])
    elif corruption == "missing_record":
        records = records[1:]
    elif corruption == "wrong_kind":
        first = records[0]
        kind = "article" if first.record_type != "article" else "amendment"
        records = (first.model_copy(update={"record_type": kind}), *records[1:])
    elif corruption == "missing_metadata":
        documents = documents[1:]
    elif corruption == "reason_with_metadata":
        records = (records[0].model_copy(update={"unavailable_reason": "Missing"}), *records[1:])
    else:
        documents = (*documents, documents[0].model_copy(update={"document_id": "doc:unused"}))
    with pytest.raises(ValidationError):
        LineageView.model_validate(
            {**view.model_dump(), "documents": documents, "source_records": records}
        )


def test_legacy_metadata_absence_remains_readable_and_does_not_fabricate_links() -> None:
    path = Path(__file__).parent / "fixtures" / "lineage" / "view.json"
    legacy = LineageView.model_validate_json(path.read_bytes())
    assert legacy.documents == legacy.source_records == ()


@pytest.mark.parametrize("unavailable", [False, True])
def test_submission_cannot_be_remapped_to_another_document(
    tmp_path: Path, unavailable: bool
) -> None:
    view = build_lineage(adopted_world(tmp_path), generated_at=LATER)
    submission = next(r for r in view.source_records if r.record_type == "document_text")
    final = next(r for r in view.source_records if r.record_type == "article")
    records = tuple(
        r.model_copy(update={"document_id": final.document_id}) if r == submission else r
        for r in view.source_records
    )
    documents = tuple(d for d in view.documents if d.document_id != submission.document_id)
    if unavailable:
        records = tuple(r.model_copy(update={"unavailable_reason": "Missing"}) for r in records)
        documents = ()
    with pytest.raises(ValidationError, match="keyed by its own document"):
        LineageView.model_validate(
            {**view.model_dump(), "documents": documents, "source_records": records}
        )
