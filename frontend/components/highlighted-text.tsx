import type { TextSpan } from "../lib/api";

/** Merge overlapping evidence spans and retain the original text and Unicode offsets. */
export function HighlightedText({
  text,
  spans,
  tone = "added",
}: {
  text: string;
  spans: readonly TextSpan[];
  tone?: "added" | "removed";
}) {
  const characters = Array.from(text);
  const ranges: { start: number; end: number }[] = [];
  for (const span of [...spans].sort((a, b) => a.start - b.start)) {
    if (span.start < 0 || span.end > characters.length || span.start >= span.end) {
      continue;
    }
    const previous = ranges.at(-1);
    if (previous && span.start <= previous.end) {
      previous.end = Math.max(previous.end, span.end);
    } else {
      ranges.push({ start: span.start, end: span.end });
    }
  }
  let cursor = 0;
  const parts = ranges.map((range) => {
    const before = characters.slice(cursor, range.start).join("");
    cursor = range.end;
    return (
      <span key={`${range.start}-${range.end}`}>
        {before}
        <mark
          className={
            tone === "removed"
              ? "rounded-sm bg-amber-100 px-0.5 text-amber-950 line-through decoration-amber-600"
              : "rounded-sm bg-teal-100 px-0.5 text-teal-950 decoration-teal-300 underline decoration-2 underline-offset-4"
          }
        >
          {characters.slice(range.start, range.end).join("")}
        </mark>
      </span>
    );
  });
  return (
    <>
      {parts}
      {characters.slice(cursor).join("")}
    </>
  );
}
