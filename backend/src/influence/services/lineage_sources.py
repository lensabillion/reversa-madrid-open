"""Attach collected provenance to the exact records a lineage view quotes."""

from influence.schemas.atlas import Amendment, ArticleVersion, SourceDocument
from influence.schemas.lineage import LineageView
from influence.schemas.lineage_sources import LineageDocument, LineageSourceRecord
from influence.services.collected import Collected, PipelineError


def attach_sources(view: LineageView, collected: Collected) -> LineageView:
    """Copy only referenced source metadata; missing metadata remains explicit.

    Indexing is linear in collected records. Sorting the R exposed record IDs and D
    referenced document IDs costs O(R log R + D log D); whole source text is not copied.
    """
    documents: dict[str, SourceDocument] = {}
    for document in collected.documents:
        previous = documents.get(document.document_id)
        if previous is not None and previous != document:
            raise PipelineError(f"Conflicting source document {document.document_id}")
        documents[document.document_id] = document
    amendments = _index_amendments(collected.amendments)
    articles = _index_articles(collected.articles)
    text_ids = {text.document_id for text in collected.document_texts}
    records: list[LineageSourceRecord] = []
    used: set[str] = set()
    for record_id, kind in sorted(view.source_record_types().items()):
        if kind == "amendment":
            amendment = amendments.get(record_id)
            if amendment is None:
                raise PipelineError(f"Missing quoted amendment {record_id}")
            document_id = amendment.document_id
            label = (
                f"Amendment {amendment.number}"
                if amendment.number is not None
                else amendment.target_provision
            )
        elif kind == "article":
            article = articles.get(record_id)
            if article is None:
                raise PipelineError(f"Missing quoted article {record_id}")
            document_id, label = article.document_id, article.provision
        else:
            if record_id not in text_ids:
                raise PipelineError(f"Missing quoted document text {record_id}")
            document_id = record_id
            document = documents.get(document_id)
            label = None if document is None else document.title
        available = document_id in documents
        if available:
            used.add(document_id)
        records.append(
            LineageSourceRecord(
                record_id=record_id,
                document_id=document_id,
                record_type=kind,
                label=label,
                unavailable_reason=None
                if available
                else "Source document metadata was not collected.",
            )
        )
    metadata = tuple(
        LineageDocument(
            document_id=document.document_id,
            url=document.url,
            title=document.title,
            source_kind=document.source_kind,
            published_at=document.published_at,
            retrieved_at=document.retrieved_at,
            sha256=document.sha256,
        )
        for document_id in sorted(used)
        for document in (documents[document_id],)
    )
    return LineageView.model_validate(
        {**view.model_dump(), "documents": metadata, "source_records": tuple(records)}
    )


def _index_amendments(records: tuple[Amendment, ...]) -> dict[str, Amendment]:
    indexed: dict[str, Amendment] = {}
    for record in records:
        previous = indexed.get(record.amendment_id)
        if previous is not None and previous != record:
            raise PipelineError(f"Conflicting amendment {record.amendment_id}")
        indexed[record.amendment_id] = record
    return indexed


def _index_articles(records: tuple[ArticleVersion, ...]) -> dict[str, ArticleVersion]:
    indexed: dict[str, ArticleVersion] = {}
    for record in records:
        previous = indexed.get(record.article_id)
        if previous is not None and previous != record:
            raise PipelineError(f"Conflicting article {record.article_id}")
        indexed[record.article_id] = record
    return indexed
