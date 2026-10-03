"use client";

import { useState } from "react";
import type { TextSpan } from "../lib/api";
import { sourceContext } from "../lib/source-context";
import { HighlightedText } from "./highlighted-text";

/** Display-only props: the GraphSnapshot adapter supplies source excerpts and verdicts. */
export interface AtlasExcerpt {
  text: string;
  language: string;
  spans: readonly TextSpan[];
  source: {
    title: string;
    url: string;
    page: number | null;
    publishedAt: string | null;
  };
}

/** Outcome and publication decisions are supplied by the pipeline, never inferred here. */
export interface AtlasEvidenceProps {
  actor: string;
  ask: string;
  assessment: {
    status: "published" | "unconfirmed" | "contradicted" | "insufficient_evidence";
    method: string;
    explanation: string;
    limitations: readonly string[];
  };
  submission: AtlasExcerpt;
  original: AtlasExcerpt | null;
  amendment: AtlasExcerpt;
  outcome: {
    status: "full" | "partial" | "not_observed" | "unknown";
    explanation: string;
    finalText: AtlasExcerpt | null;
  };
}

const assessmentLabels = {
  published: "Published link",
  unconfirmed: "Unconfirmed candidate",
  contradicted: "Contradicted candidate",
  insufficient_evidence: "Insufficient evidence",
} satisfies Record<AtlasEvidenceProps["assessment"]["status"], string>;
const outcomeLabels = {
  full: "Fully reflected in final text",
  partial: "Partially reflected in final text",
  not_observed: "Not reflected in final text",
  unknown: "Final outcome unknown",
} satisfies Record<AtlasEvidenceProps["outcome"]["status"], string>;

function publicUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

const count = new Intl.NumberFormat("en-US");

/**
 * Bounded windows around every cited span, so a long submission does not push its
 * highlight tens of thousands of pixels below the other three columns. The full source
 * stays one click away; offsets are never changed, only the visible slice.
 */
function SourceText({
  characters,
  text,
  spans,
}: {
  characters: readonly string[];
  text: string;
  spans: readonly TextSpan[];
}) {
  const [expanded, setExpanded] = useState(false);
  const segments = sourceContext(characters, spans);
  const omits = segments.some((segment) => segment.kind === "gap");
  return (
    <>
      {omits && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
          className="mb-3 block cursor-pointer font-sans text-xs font-medium text-teal-800 underline underline-offset-4"
        >
          {expanded
            ? "Show cited passages only"
            : `Show full source text (${count.format(characters.length)} characters)`}
        </button>
      )}
      {expanded || !omits ? (
        <HighlightedText text={text} spans={spans} />
      ) : (
        segments.map((segment) =>
          segment.kind === "window" ? (
            <span key={`window-${segment.start}`} className="block">
              <HighlightedText text={segment.text} spans={segment.spans} />
            </span>
          ) : (
            <span
              key={`gap-${segment.start}`}
              className="my-2 block font-sans text-xs italic text-stone-500"
            >
              … {count.format(segment.end - segment.start)} characters omitted …
            </span>
          ),
        )
      )}
    </>
  );
}

function Excerpt({
  title,
  excerpt,
  empty,
}: {
  title: string;
  excerpt: AtlasExcerpt | null;
  empty: string;
}) {
  const characters = Array.from(excerpt?.text ?? "");
  const valid =
    excerpt?.spans.every(
      (span) =>
        Number.isInteger(span.start) &&
        Number.isInteger(span.end) &&
        span.start >= 0 &&
        span.end > span.start &&
        span.end <= characters.length &&
        characters.slice(span.start, span.end).join("") === span.text,
    ) ?? true;
  const href = excerpt ? publicUrl(excerpt.source.url) : null;
  return (
    <section aria-label={title} className="min-w-0 border-t border-stone-200 pt-4">
      <h3 className="mb-4 text-xs font-semibold uppercase tracking-wider text-stone-500">
        {title}
      </h3>
      {excerpt && excerpt.text.length > 0 ? (
        <div
          lang={excerpt.language}
          className="whitespace-pre-wrap break-words font-serif text-base leading-8 text-stone-800"
        >
          <SourceText
            characters={characters}
            text={excerpt.text}
            spans={valid ? excerpt.spans : []}
          />
        </div>
      ) : (
        <p className="text-sm italic leading-6 text-stone-500">{empty}</p>
      )}
      {!valid && (
        <p role="alert" className="mt-3 text-sm text-amber-900">
          Evidence verification failed: the supplied quote does not match its source span. The
          upstream assessment has not been re-evaluated.
        </p>
      )}
      {excerpt && (
        <div className="mt-5 break-words text-xs leading-6 text-stone-500">
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-teal-800 underline underline-offset-4"
            >
              {excerpt.source.title}
            </a>
          ) : (
            <p>{excerpt.source.title} · Source link unavailable</p>
          )}
          <p>
            {excerpt.source.page === null ? "Page unspecified" : `Page ${excerpt.source.page}`} ·{" "}
            {excerpt.source.publishedAt === null
              ? "Publication date unknown"
              : `Published ${excerpt.source.publishedAt}`}
          </p>
        </div>
      )}
    </section>
  );
}

/** Four source columns retain the distinction between an echoed ask and its legal outcome. */
export function AtlasEvidence({
  actor,
  ask,
  assessment,
  submission,
  original,
  amendment,
  outcome,
}: AtlasEvidenceProps) {
  return (
    <article
      aria-label="Atlas link evidence"
      className="min-w-0 rounded-sm border border-stone-200 bg-white p-5 sm:p-8"
    >
      <header>
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
          <p className="font-medium uppercase tracking-wider text-teal-800">{actor}</p>
          <p className={assessment.status === "published" ? "text-teal-800" : "text-amber-900"}>
            {assessmentLabels[assessment.status]}
          </p>
        </div>
        <h2 className="mt-3 font-serif text-2xl leading-snug text-stone-900">{ask}</h2>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-stone-600">{assessment.explanation}</p>
      </header>
      <div className="mt-7 grid gap-7 md:grid-cols-2 xl:grid-cols-4">
        <Excerpt title="Lobby request" excerpt={submission} empty="Request wording unavailable" />
        <Excerpt
          title="Original legal text"
          excerpt={original}
          empty={
            original === null
              ? "Original wording unavailable"
              : "Known empty original: new provision"
          }
        />
        <Excerpt
          title="Proposed amendment"
          excerpt={amendment}
          empty="No replacement wording: deletion"
        />
        <Excerpt
          title="Final legal text"
          excerpt={outcome.finalText}
          empty={
            outcome.finalText === null ? "Final wording unavailable" : "Known empty final wording"
          }
        />
      </div>
      <section aria-label="Legal outcome" className="mt-7 border-t border-stone-200 pt-5">
        <h3 className="text-sm font-medium text-stone-800">{outcomeLabels[outcome.status]}</h3>
        <p className="mt-2 text-sm leading-6 text-stone-600">{outcome.explanation}</p>
      </section>
      <details className="mt-6 border-t border-stone-200 pt-4 text-xs leading-6 text-stone-500">
        <summary className="cursor-pointer font-medium text-stone-700">
          Method and limitations
        </summary>
        <p className="mt-2">Assessment method: {assessment.method}</p>
        {assessment.limitations.length > 0 && (
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {assessment.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        )}
      </details>
    </article>
  );
}
