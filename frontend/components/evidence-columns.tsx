import type { ScoreResult, SourceMatch, TextSpan } from "../lib/api";
import { HighlightedText } from "./highlighted-text";

interface EvidenceText {
  old: string | null;
  new: string;
  language: string;
}

function Wording({
  text,
  spans,
  language,
  empty,
  removed,
}: {
  text: string | null;
  spans: TextSpan[];
  language: string;
  empty: string;
  removed: boolean;
}) {
  return (
    <div
      lang={language}
      className="whitespace-pre-wrap break-words font-serif text-base leading-8 text-stone-800"
    >
      {text?.trim() ? (
        <HighlightedText text={text} spans={spans} tone={removed ? "removed" : "added"} />
      ) : (
        <p className="font-sans text-sm italic text-stone-500">{empty}</p>
      )}
    </div>
  );
}

/** Evidence offsets belong to their supplied old/new text; columns do not infer alignment. */
export function EvidenceColumns({
  amendment,
  submission,
  evidence,
  mode,
  sourceMetadata,
}: {
  amendment: EvidenceText;
  submission: EvidenceText | null;
  evidence: ScoreResult["evidence"];
  mode: "edits" | "passages";
  sourceMetadata: Pick<SourceMatch, "organization" | "document" | "page"> | null;
}) {
  const insertions = evidence.filter((item) => item.operation === "insert");
  const deletions = evidence.filter((item) => item.operation === "delete");
  const headingStyle = "mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-stone-500";
  const captionStyle = "mb-4 text-xs leading-5 text-stone-500";
  return (
    <div className="mt-6 border-t border-stone-200 pt-4">
      {evidence.length > 0 && (
        <p className="flex flex-wrap gap-5 text-xs text-stone-500">
          {insertions.length > 0 && (
            <span className="flex items-center gap-2">
              <span aria-hidden="true" className="h-2.5 w-2.5 bg-teal-200" />
              {mode === "edits" ? "Shared added wording" : "Shared wording"}
            </span>
          )}
          {deletions.length > 0 && (
            <span className="flex items-center gap-2">
              <span aria-hidden="true" className="h-2.5 w-2.5 bg-amber-200" />
              Shared removed wording
            </span>
          )}
        </p>
      )}
      <div className="grid gap-8 py-6 lg:grid-cols-3 lg:grid-rows-[auto_auto_1fr] lg:gap-y-0">
        <section
          aria-label="Before the amendment"
          className="min-w-0 lg:row-span-3 lg:grid lg:grid-rows-subgrid"
        >
          <h3 className={headingStyle}>Before the amendment</h3>
          <p className={captionStyle}>The draft wording the lawmaker wants to change.</p>
          <div className="min-w-0">
            <Wording
              text={amendment.old}
              spans={deletions.map((item) => item.amendment)}
              language={amendment.language}
              empty={
                amendment.old === null
                  ? "Original wording not supplied"
                  : "No original wording (insertion)"
              }
              removed
            />
          </div>
        </section>
        <section
          aria-label="Lawmaker's proposal"
          className="min-w-0 lg:row-span-3 lg:grid lg:grid-rows-subgrid"
        >
          <h3 className={headingStyle}>Lawmaker's proposal</h3>
          <p className={captionStyle}>The wording the lawmaker proposes instead.</p>
          <div className="min-w-0">
            <Wording
              text={amendment.new}
              spans={insertions.map((item) => item.amendment)}
              language={amendment.language}
              empty={
                amendment.old?.trim()
                  ? "No proposed wording (deletion)"
                  : "Proposed wording not supplied"
              }
              removed={false}
            />
          </div>
        </section>
        <section
          aria-label="Lobby's proposal"
          className="min-w-0 lg:row-span-3 lg:grid lg:grid-rows-subgrid"
        >
          <h3 className={headingStyle}>Lobby's proposal</h3>
          <p className={captionStyle}>
            {submission
              ? sourceMetadata
                ? `The wording requested by ${sourceMetadata.organization}.`
                : "The wording supplied in the lobby submission or comment."
              : ""}
          </p>
          <div className="min-w-0">
            {submission ? (
              <>
                <Wording
                  text={submission.new}
                  spans={insertions.map((item) => item.submission)}
                  language={submission.language}
                  empty={
                    submission.old?.trim()
                      ? "No proposed wording (deletion)"
                      : "Proposed wording not supplied"
                  }
                  removed={false}
                />
                {sourceMetadata && (
                  <p className="mt-4 break-all text-xs leading-5 text-stone-500">
                    {sourceMetadata.document} · p. {sourceMetadata.page}
                  </p>
                )}
                {submission.old?.trim() && (
                  <details
                    open={deletions.length > 0 && insertions.length === 0}
                    className="mt-5 border-t border-stone-200 pt-3"
                  >
                    <summary className="mb-3 w-fit cursor-pointer text-xs font-medium text-stone-600">
                      Original lobby wording
                    </summary>
                    <Wording
                      text={submission.old}
                      spans={deletions.map((item) => item.submission)}
                      language={submission.language}
                      empty="Original wording not supplied"
                      removed
                    />
                  </details>
                )}
              </>
            ) : (
              <p className="text-sm italic text-stone-500">No lobby submission available</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
