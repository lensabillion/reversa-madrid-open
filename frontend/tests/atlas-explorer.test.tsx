// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { AtlasExplorer, type AtlasLinkView } from "../components/atlas-explorer";

const base: AtlasLinkView = {
  id: "link-1",
  law: "Example law",
  topics: ["Health"],
  year: 2024,
  evidence: {
    actor: "Example association",
    ask: "Retain records",
    assessment: {
      status: "published",
      method: "test-v1",
      explanation: "Fixture only",
      limitations: [],
    },
    submission: {
      text: "Retain records.",
      language: "en",
      spans: [],
      source: { title: "Example paper", url: "https://example.org", page: null, publishedAt: null },
    },
    original: null,
    amendment: {
      text: "Retain records.",
      language: "en",
      spans: [],
      source: { title: "Amendment", url: "https://example.org/am", page: null, publishedAt: null },
    },
    outcome: { status: "unknown", explanation: "Not yet assessed", finalText: null },
  },
};
const candidate: AtlasLinkView = {
  ...base,
  id: "candidate-2",
  evidence: {
    ...base.evidence,
    actor: "Unconfirmed group",
    assessment: { ...base.evidence.assessment, status: "unconfirmed" },
  },
};
afterEach(cleanup);

test("keeps unconfirmed candidates out of published links until audit view is selected", () => {
  render(
    <AtlasExplorer links={[base, candidate]} coverageNotes={["Only one source downloaded"]} />,
  );
  expect(screen.queryByRole("button", { name: /Unconfirmed group/ })).toBeNull();
  expect(screen.getByRole("button", { name: /Example association/ })).toBeDefined();
  expect(screen.getByText("Only one source downloaded")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Audit candidates" }));
  expect(screen.getByRole("button", { name: /Unconfirmed group/ })).toBeDefined();
  expect(screen.queryByRole("button", { name: /Example association/ })).toBeNull();
  expect(screen.getByText("Unconfirmed candidate")).toBeDefined();
});

test("filters laws and actors, resets selection, and shows honest empty states", () => {
  const second = {
    ...base,
    id: "other",
    law: "Energy law",
    topics: ["Energy"],
    year: 2025,
    evidence: { ...base.evidence, actor: "Energy association" },
  };
  render(<AtlasExplorer links={[base, second]} coverageNotes={[]} />);
  fireEvent.change(screen.getByRole("combobox", { name: "Topic" }), {
    target: { value: "Energy" },
  });
  expect(
    screen.getByRole("button", { name: /Energy association/ }).getAttribute("aria-pressed"),
  ).toBe("true");
  expect(screen.queryByRole("button", { name: /Example association/ })).toBeNull();
  fireEvent.change(screen.getByRole("searchbox", { name: "Search loaded laws and actors" }), {
    target: { value: "no match" },
  });
  expect(screen.getByText("No published links match these filters.")).toBeDefined();
  expect(screen.queryByRole("article", { name: "Atlas link evidence" })).toBeNull();
});

test("empty input reports unavailable published evidence without claiming no influence", () => {
  render(<AtlasExplorer links={[]} coverageNotes={["Awaiting pipeline records"]} />);
  expect(screen.getByText("No published links available in this snapshot.")).toBeDefined();
  expect(screen.getByText("Awaiting pipeline records")).toBeDefined();
});

test("keeps unavailable selected filters visible when a snapshot is replaced", () => {
  const { rerender } = render(<AtlasExplorer links={[base]} coverageNotes={[]} />);
  fireEvent.change(screen.getByRole("combobox", { name: "Topic" }), {
    target: { value: "Health" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "Procedure year" }), {
    target: { value: "2024" },
  });
  rerender(
    <AtlasExplorer
      links={[{ ...base, id: "new", topics: ["Energy"], year: 2025 }]}
      coverageNotes={[]}
    />,
  );
  expect(screen.getByRole("option", { name: "Health (unavailable)" })).toBeDefined();
  expect(screen.getByRole("option", { name: "2024 (unavailable)" })).toBeDefined();
  expect(screen.getByText("No published links match these filters.")).toBeDefined();
  fireEvent.change(screen.getByRole("combobox", { name: "Topic" }), { target: { value: "" } });
  fireEvent.change(screen.getByRole("combobox", { name: "Procedure year" }), {
    target: { value: "" },
  });
  expect(screen.getByRole("button", { name: /Example association/ })).toBeDefined();
});

test("filters a law by each of its supplied topics", () => {
  render(<AtlasExplorer links={[{ ...base, topics: ["Health", "Energy"] }]} coverageNotes={[]} />);
  fireEvent.change(screen.getByRole("combobox", { name: "Topic" }), {
    target: { value: "Energy" },
  });
  expect(screen.getByRole("button", { name: /Example association/ })).toBeDefined();
  expect(screen.getByRole("status").textContent).toContain("1 of 1");
});
