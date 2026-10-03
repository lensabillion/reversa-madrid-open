// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { AtlasEvidence, type AtlasEvidenceProps } from "../components/atlas-evidence";

const excerpt = {
  text: "😀 Operators shall retain records.",
  language: "en",
  spans: [{ start: 12, end: 17, text: "shall" }],
  source: {
    title: "Published position paper",
    url: "https://example.org/paper.pdf",
    page: 2,
    publishedAt: "2023-02-01",
  },
};
const props: AtlasEvidenceProps = {
  actor: "Example association",
  ask: "Require operators to retain records.",
  assessment: {
    status: "published",
    method: "evaluated-method-v1",
    explanation: "The request and amendment introduce the same obligation.",
    limitations: ["Text reuse does not establish causal authorship."],
  },
  submission: excerpt,
  original: { ...excerpt, text: "Operators may retain records.", spans: [] },
  amendment: excerpt,
  outcome: {
    status: "unknown",
    explanation: "The final text has not been supplied.",
    finalText: null,
  },
};
afterEach(cleanup);

test("shows exact Unicode evidence and provenance without inventing a final outcome", () => {
  render(<AtlasEvidence {...props} />);
  const ask = screen.getByRole("region", { name: "Lobby request" });
  expect(ask.querySelector("mark")?.textContent).toBe("shall");
  expect(
    within(ask).getByRole("link", { name: "Published position paper" }).getAttribute("href"),
  ).toBe("https://example.org/paper.pdf");
  expect(within(ask).getByText("Page 2 · Published 2023-02-01")).toBeDefined();
  expect(screen.getByText("Final outcome unknown")).toBeDefined();
  expect(screen.getByText("The final text has not been supplied.")).toBeDefined();
  expect(screen.queryByText("Not reflected in final text")).toBeNull();
});

test("rejects inaccurate quoted spans and unsafe source URLs", () => {
  render(
    <AtlasEvidence
      {...props}
      submission={{
        ...excerpt,
        spans: [{ start: 12, end: 17, text: "may" }],
        source: { ...excerpt.source, url: "javascript:alert(1)" },
      }}
    />,
  );
  const ask = screen.getByRole("region", { name: "Lobby request" });
  expect(ask.querySelector("mark")).toBeNull();
  expect(within(ask).getByRole("alert").textContent).toContain("Evidence verification failed");
  expect(within(ask).queryByRole("link")).toBeNull();
  expect(ask.textContent).toContain(excerpt.text);
});

test.each(["unconfirmed", "contradicted"] as const)(
  "labels %s assessments separately",
  (status) => {
    render(
      <AtlasEvidence {...props} assessment={{ ...props.assessment, status }} original={null} />,
    );
    expect(
      screen.getByText(
        status === "unconfirmed" ? "Unconfirmed candidate" : "Contradicted candidate",
      ),
    ).toBeDefined();
    expect(screen.queryByText("Published link")).toBeNull();
    expect(screen.getByText("Original wording unavailable")).toBeDefined();
  },
);

test("retains known empty original and deletion amendments", () => {
  const { rerender } = render(
    <AtlasEvidence {...props} original={{ ...excerpt, text: "", spans: [] }} />,
  );
  expect(screen.getByText("Known empty original: new provision")).toBeDefined();
  rerender(<AtlasEvidence {...props} amendment={{ ...excerpt, text: "", spans: [] }} />);
  expect(screen.getByText("No replacement wording: deletion")).toBeDefined();
});

test("renders partial outcome evidence without upgrading it to a full win", () => {
  render(
    <AtlasEvidence
      {...props}
      outcome={{
        status: "partial",
        explanation: "Only the record-keeping obligation remains.",
        finalText: excerpt,
      }}
    />,
  );
  const final = screen.getByRole("region", { name: "Final legal text" });
  expect(final.querySelector("mark")?.textContent).toBe("shall");
  expect(screen.getByText("Partially reflected in final text")).toBeDefined();
  expect(screen.queryByText("Fully reflected in final text")).toBeNull();
});

test("distinguishes a known empty final provision from unavailable final text", () => {
  render(
    <AtlasEvidence
      {...props}
      outcome={{
        status: "full",
        explanation: "The requested deletion is reflected in the final act.",
        finalText: { ...excerpt, text: "", spans: [] },
      }}
    />,
  );
  const final = screen.getByRole("region", { name: "Final legal text" });
  expect(within(final).getByText("Known empty final wording")).toBeDefined();
  expect(within(final).queryByText("Final wording unavailable")).toBeNull();
  expect(within(final).getByRole("link", { name: "Published position paper" })).toBeDefined();
});

/** Deterministic filler of exactly `length` code points (ASCII, so UTF-16 length agrees). */
function filler(length: number, offset = 0): string {
  let text = "";
  for (let index = offset; text.length < length; index += 1) {
    text += `recital ${index % 89} considers the market. `;
  }
  return text.slice(0, length);
}

function omitted(region: HTMLElement): number[] {
  return [...(region.textContent ?? "").matchAll(/… ([\d,]+) characters omitted …/gu)].map(
    (match) => Number(match[1]?.replaceAll(",", "")),
  );
}

test("short fixture sources render whole, with no expand control", () => {
  render(<AtlasEvidence {...props} />);
  const ask = screen.getByRole("region", { name: "Lobby request" });
  expect(within(ask).queryByRole("button")).toBeNull();
  expect(omitted(ask)).toEqual([]);
});

test("a late highlight in a 44,114-character submission shows beside its amendment and expands", () => {
  const quote = "providers shall keep automatically generated logs";
  const before = `😀 ${filler(40_000 - 2)}🇪🇺 `;
  const start = Array.from(before).length;
  const text = before + quote + filler(44_114 - start - quote.length, 11);
  expect(Array.from(text).length).toBe(44_114);
  render(
    <AtlasEvidence
      {...props}
      submission={{ ...excerpt, text, spans: [{ start, end: start + quote.length, text: quote }] }}
    />,
  );
  const ask = screen.getByRole("region", { name: "Lobby request" });
  expect(ask.querySelector("mark")?.textContent).toBe(quote);
  expect(ask.textContent).toContain(`🇪🇺 ${quote}`);
  expect(ask.textContent?.length).toBeLessThan(1_500);
  const gaps = omitted(ask);
  expect(gaps).toHaveLength(2);
  const shown = Array.from(ask.querySelector("[lang]")?.textContent ?? "").length;
  expect(gaps[0]).toBeGreaterThan(39_000);
  expect(shown).toBeLessThan(1_000);
  const amendment = screen.getByRole("region", { name: "Proposed amendment" });
  expect(amendment.querySelector("mark")?.textContent).toBe("shall");
  expect(within(ask).getByRole("link", { name: "Published position paper" })).toBeDefined();

  const expand = within(ask).getByRole("button", {
    name: "Show full source text (44,114 characters)",
  });
  expect(expand.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(expand);
  expect(ask.textContent).toContain(text);
  expect(ask.querySelector("mark")?.textContent).toBe(quote);
  expect(omitted(ask)).toEqual([]);
  const collapse = within(ask).getByRole("button", { name: "Show cited passages only" });
  expect(collapse.getAttribute("aria-expanded")).toBe("true");
  fireEvent.click(collapse);
  expect(omitted(ask)).toEqual(gaps);
});

test("distant spans in one long source each get a window, none dropped", () => {
  const text = `😀${filler(50_000)}`;
  const characters = Array.from(text);
  const spans = [1_000, 25_000, 48_000].map((start) => ({
    start,
    end: start + 20,
    text: characters.slice(start, start + 20).join(""),
  }));
  render(<AtlasEvidence {...props} submission={{ ...excerpt, text, spans }} />);
  const ask = screen.getByRole("region", { name: "Lobby request" });
  expect([...ask.querySelectorAll("mark")].map((mark) => mark.textContent)).toEqual(
    spans.map((span) => span.text),
  );
  const gaps = omitted(ask);
  expect(gaps).toHaveLength(4);
  const visible = [...ask.querySelectorAll("[lang] > span.block")]
    .filter((node) => !node.textContent?.includes("characters omitted"))
    .map((node) => Array.from(node.textContent ?? "").length);
  expect(visible).toHaveLength(3);
  expect([...gaps, ...visible].reduce((sum, size) => sum + size, 0)).toBe(characters.length);
});
