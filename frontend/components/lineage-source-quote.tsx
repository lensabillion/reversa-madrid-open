import type { LineageMatchKind } from "../lib/lineage-api";
import { type LineageSourceIndex, quotationSource, safeSourceUrl } from "../lib/lineage-sources";
import type { SourceSpan } from "../lib/source-span";
import { kindStyle } from "./lineage-kind";

/** The saved quotation and its explicit record-to-document provenance; no inferred links. */
export function SourceQuote({
  span,
  label,
  kind,
  sources,
}: {
  span: SourceSpan;
  label: string;
  kind: LineageMatchKind;
  sources: LineageSourceIndex;
}) {
  const source = quotationSource(span, sources);
  const document = source.document;
  const url = document === null ? null : safeSourceUrl(document.url);
  return (
    <figure className="space-y-2">
      <blockquote
        className={`border-l-4 ${kindStyle[kind].border} bg-white px-3 py-2 font-serif text-[15px] leading-6 text-stone-900`}
      >
        <span className="sr-only">{label}: </span>
        {span.text}
      </blockquote>
      <figcaption className="space-y-1 text-xs leading-5 text-stone-600">
        <p className="break-all font-mono">
          Record {span.record_id} · field {span.field}
        </p>
        <p>
          Unicode code-point offsets [{span.start}, {span.end}): start included, end excluded,
          within this extracted record field.
        </p>
        {span.page !== null && <p>Recorded page {span.page}; no page-specific URL was saved.</p>}
        {document === null ? (
          <p className="text-amber-900">Source unavailable: {source.reason}</p>
        ) : (
          <>
            {url === null ? (
              <p className="text-amber-900">
                Source link unavailable: saved URL is not HTTP or HTTPS.
              </p>
            ) : (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-teal-800 underline underline-offset-2"
              >
                {document.source_kind === "parltrack"
                  ? "Open Parltrack dataset source"
                  : "Open original source"}
              </a>
            )}
            <p>
              {source.record?.label ?? document.title ?? document.document_id} · source kind{" "}
              {document.source_kind}
            </p>
            <p>
              Published{" "}
              {document.published_at === null ? (
                "date unknown"
              ) : (
                <time dateTime={document.published_at}>{document.published_at}</time>
              )}{" "}
              · retrieved <time dateTime={document.retrieved_at}>{document.retrieved_at}</time>
            </p>
            <details>
              <summary className="cursor-pointer">Saved document identity and SHA-256</summary>
              <p className="break-all font-mono">{document.document_id}</p>
              <p className="break-all font-mono">SHA-256 {document.sha256}</p>
            </details>
          </>
        )}
      </figcaption>
    </figure>
  );
}
