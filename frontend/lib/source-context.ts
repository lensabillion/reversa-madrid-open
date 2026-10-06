import type { TextSpan } from "../components/highlighted-text";

/** Code points of context kept on each side of a cited span (about nine lines in one column). */
export const CONTEXT_CODE_POINTS = 300;
/** Gaps shorter than this are shown instead of omitted, so a marker never hides a few words. */
export const MIN_OMITTED_CODE_POINTS = 100;
/** How far a window edge may move to land on whitespace instead of cutting a word. */
const WORD_SNAP_CODE_POINTS = 40;

export type SourceSegment =
  | {
      kind: "window";
      /** Code-point offsets of this window in the full source. */
      start: number;
      end: number;
      text: string;
      /** The cited spans inside this window, rebased to the window's own offsets. */
      spans: TextSpan[];
    }
  | { kind: "gap"; start: number; end: number };

const whitespace = /\s/u;

/**
 * Split a source into bounded windows around every cited span and the gaps between them.
 *
 * Offsets are Unicode code points, so `characters` is `Array.from(text)`. Each span lies
 * whole inside exactly one window; windows and gaps partition `[0, characters.length)`
 * in order, and every gap is at least `MIN_OMITTED_CODE_POINTS` long. Without spans the
 * opening of the source is shown. Runs in O(n + k·w) for n code points, k spans and w
 * windows; designed for submissions of up to a few hundred thousand code points and the
 * handful of spans one link cites.
 */
export function sourceContext(
  characters: readonly string[],
  spans: readonly TextSpan[],
  context: number = CONTEXT_CODE_POINTS,
): SourceSegment[] {
  const length = characters.length;
  if (length === 0) {
    return [];
  }
  const sorted = [...spans].sort((a, b) => a.start - b.start || a.end - b.end);
  const ranges: { start: number; end: number }[] = [];
  for (const range of sorted.length > 0
    ? sorted.map((span) => snap(characters, span.start, span.end, context))
    : [{ start: 0, end: Math.min(length, 2 * context) }]) {
    const start = range.start < MIN_OMITTED_CODE_POINTS ? 0 : range.start;
    const end = length - range.end < MIN_OMITTED_CODE_POINTS ? length : range.end;
    const previous = ranges.at(-1);
    if (previous && start - previous.end < MIN_OMITTED_CODE_POINTS) {
      previous.end = Math.max(previous.end, end);
    } else {
      ranges.push({ start, end });
    }
  }
  const segments: SourceSegment[] = [];
  let cursor = 0;
  for (const range of ranges) {
    if (range.start > cursor) {
      segments.push({ kind: "gap", start: cursor, end: range.start });
    }
    segments.push({
      kind: "window",
      start: range.start,
      end: range.end,
      text: characters.slice(range.start, range.end).join(""),
      spans: sorted
        .filter((span) => span.start >= range.start && span.end <= range.end)
        .map((span) => ({
          start: span.start - range.start,
          end: span.end - range.start,
          text: span.text,
        })),
    });
    cursor = range.end;
  }
  if (cursor < length) {
    segments.push({ kind: "gap", start: cursor, end: length });
  }
  return segments;
}

/** Widen a span by `context`, then pull each edge to whitespace without exposing a cut word. */
function snap(
  characters: readonly string[],
  spanStart: number,
  spanEnd: number,
  context: number,
): { start: number; end: number } {
  let start = Math.max(0, spanStart - context);
  let end = Math.min(characters.length, spanEnd + context);
  if (start > 0) {
    const limit = Math.min(spanStart, start + WORD_SNAP_CODE_POINTS);
    for (let index = start; index < limit; index += 1) {
      if (whitespace.test(characters[index] ?? "")) {
        start = index + 1;
        break;
      }
    }
  }
  if (end < characters.length) {
    const limit = Math.max(spanEnd, end - WORD_SNAP_CODE_POINTS);
    for (let index = end - 1; index >= limit; index -= 1) {
      if (whitespace.test(characters[index] ?? "")) {
        end = index;
        break;
      }
    }
  }
  return { start, end };
}
