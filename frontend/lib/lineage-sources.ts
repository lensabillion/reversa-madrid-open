import type { LineageDocumentRecord, LineageSourceRecord, LineageView } from "./lineage-api";
import type { SourceSpan } from "./source-span";

export interface LineageSourceIndex {
  documents: ReadonlyMap<string, LineageDocumentRecord>;
  records: ReadonlyMap<string, LineageSourceRecord>;
}

/** Index compact saved metadata once, never fetching or guessing from a record ID. */
export function indexLineageSources(view: LineageView): LineageSourceIndex {
  const documents = new Map(
    (view.documents ?? []).map((document) => [document.document_id, document]),
  );
  const records = new Map((view.source_records ?? []).map((record) => [record.record_id, record]));
  if (
    documents.size !== (view.documents ?? []).length ||
    records.size !== (view.source_records ?? []).length
  ) {
    throw new Error("Duplicate source metadata identifiers");
  }
  return { documents, records };
}

/** Allow web links only; return the saved URL unchanged, without invented page fragments. */
export function safeSourceUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? value : null;
  } catch {
    return null;
  }
}

/** Resolve the source of this exact field, with explicit unavailable states for old snapshots. */
export function quotationSource(
  span: SourceSpan,
  sources: LineageSourceIndex,
): {
  document: LineageDocumentRecord | null;
  record: LineageSourceRecord | null;
  reason: string | null;
} {
  const record = sources.records.get(span.record_id);
  if (record === undefined) {
    return {
      document: null,
      record: null,
      reason: "this snapshot has no source metadata for this quotation",
    };
  }
  if (
    (record.record_type !== "amendment" && span.field !== "text") ||
    (record.record_type === "amendment" && span.field === "text") ||
    (record.record_type === "document_text" && record.record_id !== record.document_id)
  ) {
    return {
      document: null,
      record,
      reason: "saved source identity or record field does not match this quotation",
    };
  }
  if (record.unavailable_reason !== null) {
    return { document: null, record, reason: record.unavailable_reason };
  }
  const document = sources.documents.get(record.document_id);
  return document === undefined
    ? { document: null, record, reason: `document metadata is missing for ${record.document_id}` }
    : { document, record, reason: null };
}
