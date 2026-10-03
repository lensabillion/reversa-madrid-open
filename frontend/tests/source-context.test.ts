import { expect, test } from "vitest";
import type { TextSpan } from "../lib/api";
import {
  CONTEXT_CODE_POINTS,
  MIN_OMITTED_CODE_POINTS,
  type SourceSegment,
  sourceContext,
} from "../lib/source-context";

/** Deterministic legal-looking filler of exactly `length` code points. */
function filler(length: number, offset = 0): string {
  const words: string[] = [];
  let size = 0;
  for (let index = offset; size < length; index += 1) {
    const word = `clause${index % 97} `;
    words.push(word);
    size += word.length;
  }
  return words.join("").slice(0, length);
}

function spanAt(characters: readonly string[], start: number, end: number): TextSpan {
  return { start, end, text: characters.slice(start, end).join("") };
}

/** The invariants every result must keep, whatever the input. */
function assertPartition(
  characters: readonly string[],
  spans: readonly TextSpan[],
  segments: readonly SourceSegment[],
): void {
  let cursor = 0;
  let rebased = 0;
  for (const [index, segment] of segments.entries()) {
    expect(segment.start).toBe(cursor);
    expect(segment.end).toBeGreaterThan(segment.start);
    if (segment.kind === "gap") {
      expect(segment.end - segment.start).toBeGreaterThanOrEqual(MIN_OMITTED_CODE_POINTS);
      expect(segments[index + 1]?.kind ?? "window").toBe("window");
    } else {
      const window = Array.from(segment.text);
      expect(segment.text).toBe(characters.slice(segment.start, segment.end).join(""));
      for (const span of segment.spans) {
        expect(window.slice(span.start, span.end).join("")).toBe(span.text);
        expect(
          characters.slice(segment.start + span.start, segment.start + span.end).join(""),
        ).toBe(span.text);
      }
      rebased += segment.spans.length;
    }
    cursor = segment.end;
  }
  expect(cursor).toBe(characters.length);
  expect(rebased).toBe(spans.length);
}

const quote = "providers shall keep automatically generated logs";

test("a late highlight in a 44,114-code-point submission gets one bounded window", () => {
  const before = `😀 ${filler(40_000 - 2)}🇪🇺 `;
  const prefix = Array.from(before).length;
  const text = before + quote + filler(44_114 - prefix - quote.length, 7);
  const characters = Array.from(text);
  expect(characters.length).toBe(44_114);
  expect(text.length).toBeGreaterThan(characters.length);
  const span = spanAt(characters, prefix, prefix + quote.length);
  expect(span.text).toBe(quote);

  const segments = sourceContext(characters, [span]);
  assertPartition(characters, [span], segments);
  expect(segments.map((segment) => segment.kind)).toEqual(["gap", "window", "gap"]);
  const window = segments[1];
  if (window?.kind !== "window") {
    throw new Error("expected a window");
  }
  expect(window.text).toContain(`🇪🇺 ${quote}`);
  expect(window.spans).toEqual([
    { start: prefix - window.start, end: prefix - window.start + quote.length, text: quote },
  ]);
  expect(window.end - window.start).toBeLessThanOrEqual(2 * CONTEXT_CODE_POINTS + quote.length);
  expect(window.end - window.start).toBeGreaterThan(2 * (CONTEXT_CODE_POINTS - 40));
});

test("distant spans each keep their own window, none dropped, with gaps between", () => {
  const characters = Array.from(`😀${filler(60_000)}`);
  const spans = [
    spanAt(characters, 51_000, 51_040),
    spanAt(characters, 2_000, 2_030),
    spanAt(characters, 30_000, 30_010),
  ];
  const segments = sourceContext(characters, spans);
  assertPartition(characters, spans, segments);
  expect(segments.map((segment) => segment.kind)).toEqual([
    "gap",
    "window",
    "gap",
    "window",
    "gap",
    "window",
    "gap",
  ]);
  expect(
    segments.flatMap((segment) =>
      segment.kind === "window" ? segment.spans.map((span) => span.text) : [],
    ),
  ).toEqual([spans[1]?.text, spans[2]?.text, spans[0]?.text]);
});

test("nearby and overlapping spans share a window, and short texts are shown whole", () => {
  const characters = Array.from(filler(5_000));
  const spans = [
    spanAt(characters, 2_000, 2_400),
    spanAt(characters, 2_100, 2_150),
    spanAt(characters, 2_450, 2_460),
  ];
  const segments = sourceContext(characters, spans);
  assertPartition(characters, spans, segments);
  expect(segments.map((segment) => segment.kind)).toEqual(["gap", "window", "gap"]);

  const short = Array.from("😀 Operators shall retain records.");
  const shortSpans = [spanAt(short, 12, 17)];
  expect(sourceContext(short, shortSpans)).toEqual([
    {
      kind: "window",
      start: 0,
      end: short.length,
      text: short.join(""),
      spans: [{ start: 12, end: 17, text: "shall" }],
    },
  ]);
});

test("a long source without spans opens on its first passage", () => {
  const characters = Array.from(filler(10_000));
  const segments = sourceContext(characters, []);
  assertPartition(characters, [], segments);
  expect(segments).toMatchObject([
    { kind: "window", start: 0, end: 2 * CONTEXT_CODE_POINTS },
    { kind: "gap", start: 2 * CONTEXT_CODE_POINTS, end: 10_000 },
  ]);
  expect(sourceContext([], [])).toEqual([]);
});

test("windows partition random sources with non-BMP characters and keep exact quotes", () => {
  const alphabet = ["a", "b", " ", "\n", "😀", "🇪", "é", "語"];
  for (let seed = 1; seed <= 300; seed += 1) {
    let state = seed;
    const next = (limit: number): number => {
      state = (state * 1_103_515_245 + 12_345) % 2_147_483_648;
      return state % limit;
    };
    const length = next(8_000);
    const characters = Array.from({ length }, () => alphabet[next(alphabet.length)] ?? "a");
    const spans = Array.from({ length: length === 0 ? 0 : next(5) }, () => {
      const start = next(length);
      return spanAt(characters, start, start + 1 + next(Math.min(500, length - start)));
    });
    try {
      assertPartition(characters, spans, sourceContext(characters, spans));
    } catch (error) {
      throw new Error(`seed ${seed} failed`, { cause: error });
    }
  }
});
