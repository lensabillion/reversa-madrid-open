// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
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
  expect(within(ask).getByRole("alert").textContent).toContain("Evidence highlight unavailable");
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
