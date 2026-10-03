// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AtlasExplorer } from "../components/atlas-explorer";
import type { AtlasGraphSnapshot } from "../components/atlas-graph";
import { type AtlasDataNotice, AtlasWorkspace } from "../components/atlas-workspace";
import { type AtlasBundle, atlasLinkViews } from "../lib/atlas";

// Isolate the graph renderer while exercising the real workspace-to-evidence handoff.
vi.mock("../components/atlas-graph", () => ({
  AtlasGraph: ({ onSelectLink }: { onSelectLink?: (linkId: string) => void }) => (
    <section aria-label="Graph display">
      <button type="button" onClick={() => onSelectLink?.("link:a-am1-makers")}>
        Read widget evidence
      </button>
      <button type="button" onClick={() => onSelectLink?.("link:b-am3-labels")}>
        Read label evidence
      </button>
    </section>
  ),
}));

/** Shared JSONL is generated and validated against the backend atlas-1 contracts. */
function records<T>(name: string): T[] {
  return readFileSync(
    resolve(process.cwd(), "../backend/tests/fixtures/atlas", `${name}.jsonl`),
    "utf8",
  )
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as T);
}
const bundle: AtlasBundle = {
  laws: records("laws"),
  documents: records("documents"),
  documentTexts: records("document_texts"),
  passages: records("passages"),
  actors: records("actors"),
  asks: records("asks"),
  amendments: records("amendments"),
  articles: records("articles"),
  links: records("links"),
  outcomes: records("outcomes"),
};
const links = atlasLinkViews(bundle);
const snapshot: AtlasGraphSnapshot = { snapshot_id: "workspace-test", nodes: [], edges: [] };
const notice = "Invented contract fixtures only; no real influence findings.";

function workspace(
  suppliedLinks = links,
  dataNotice: AtlasDataNotice = {
    summary: "Demonstration data only; no real findings.",
    details: [notice],
  },
) {
  return (
    <AtlasWorkspace
      snapshot={snapshot}
      links={suppliedLinks}
      coverage={[]}
      coverageNotes={["Synthetic source coverage"]}
      dataNotice={dataNotice}
      analysis={<p>Supplied outcome table</p>}
    />
  );
}
afterEach(cleanup);

test("opens on the graph with a readable investigation guide and the supplied data notice", () => {
  render(workspace());
  expect(screen.getByRole("heading", { name: "Whose requests appear in EU law?" })).toBeDefined();
  expect(screen.getByRole("list", { name: "How to read the investigation" })).toBeDefined();
  expect(screen.getByText(notice)).toBeDefined();
  expect(screen.getByRole("region", { name: "Graph display" })).toBeDefined();
  expect(
    screen.getByRole("button", { name: "Explore the graph" }).getAttribute("aria-pressed"),
  ).toBe("true");
  expect(screen.queryByRole("article", { name: "Atlas link evidence" })).toBeNull();
  expect(screen.queryByText("Supplied outcome table")).toBeNull();
});

test("switches to supplied outcomes and back without claiming unknown outcomes are failures", () => {
  render(workspace());
  fireEvent.click(screen.getByRole("button", { name: "See the outcomes" }));
  const outcomes = screen.getByRole("region", { name: "What reached the final law" });
  expect(within(outcomes).getByText("Supplied outcome table")).toBeDefined();
  expect(within(outcomes).getByText(/Requests with unknown outcomes stay separate/)).toBeDefined();
  expect(
    screen.getByRole("button", { name: "See the outcomes" }).getAttribute("aria-pressed"),
  ).toBe("true");
  expect(screen.queryByRole("region", { name: "Graph display" })).toBeNull();
  expect(screen.getByText(notice)).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Explore the graph" }));
  expect(screen.getByRole("region", { name: "Graph display" })).toBeDefined();
  expect(screen.queryByText("Supplied outcome table")).toBeNull();
});

test("keeps long warnings inside collapsed details and lets readers expand and close them", () => {
  const identifier = `ask:passage-doc-hys_attachment-${"a".repeat(160)}-14`;
  const warning = `5 asks were excluded before retrieval. ${identifier}: at most 800 tokens.`;
  const summary = "Counts represent submission passages, not distinct requests.";
  render(workspace(links, { summary, details: [notice, warning] }));

  const section = screen.getByRole("region", { name: "About these results" });
  const details = section.querySelector("details");
  if (details === null) {
    throw new Error("Data details disclosure missing");
  }
  expect(details.open).toBe(false);
  expect(within(section).getByText(summary).closest("details")).toBeNull();
  expect(within(section).getByText(warning).closest("details")).toBe(details);
  expect(within(section).getByText(notice).closest("details")).toBe(details);
  expect(screen.getByRole("region", { name: "Graph display" })).toBeDefined();

  const toggle = within(section).getByText("Coverage, methods and excluded records");
  fireEvent.click(toggle);
  expect(details.open).toBe(true);
  expect(within(details).getByText(warning).textContent).toContain(identifier);
  fireEvent.click(toggle);
  expect(details.open).toBe(false);
});

test("graph callbacks open the exact link and a later graph selection replaces evidence selection", () => {
  render(workspace());
  fireEvent.click(screen.getByRole("button", { name: "Read label evidence" }));
  const evidence = screen.getByRole("article", { name: "Atlas link evidence" });
  expect(
    within(evidence).getByRole("heading", {
      name: "Print the energy grade as large as the product name",
    }),
  ).toBeDefined();
  expect(within(evidence).getByText("Final outcome unknown")).toBeDefined();
  expect(
    screen.getByRole("button", { name: "Read the evidence" }).getAttribute("aria-pressed"),
  ).toBe("true");
  expect(screen.getByRole("button", { name: /Label Alliance/ }).getAttribute("aria-pressed")).toBe(
    "true",
  );
  expect(screen.queryByRole("region", { name: "Graph display" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Explore the graph" }));
  fireEvent.click(screen.getByRole("button", { name: "Read widget evidence" }));
  expect(
    within(screen.getByRole("article", { name: "Atlas link evidence" })).getByRole("heading", {
      name: "Keep logs for at least six months",
    }),
  ).toBeDefined();
  expect(
    screen.getByRole("button", { name: /Widget Makers Europe/ }).getAttribute("aria-pressed"),
  ).toBe("true");
  expect(screen.getByRole("button", { name: /Label Alliance/ }).getAttribute("aria-pressed")).toBe(
    "false",
  );
});

test("an initial selection cannot expose an audit candidate in the published evidence view", () => {
  render(<AtlasExplorer links={links} coverageNotes={[]} initialSelectedId="link:a-am1-watch" />);
  const evidence = screen.getByRole("article", { name: "Atlas link evidence" });
  expect(within(evidence).getByText("Published link")).toBeDefined();
  expect(within(evidence).queryByText("Contradicted candidate")).toBeNull();
  expect(screen.queryByRole("button", { name: /Consumer Watch/ })).toBeNull();
});

test.each(["missing", "unpublished"] as const)(
  "a graph link with %s evidence cannot silently open another link",
  (state) => {
    const suppliedLinks =
      state === "missing"
        ? links.filter((link) => link.id !== "link:b-am3-labels")
        : links.map((link) =>
            link.id === "link:b-am3-labels"
              ? {
                  ...link,
                  evidence: {
                    ...link.evidence,
                    assessment: { ...link.evidence.assessment, status: "unconfirmed" as const },
                  },
                }
              : link,
          );
    render(workspace(suppliedLinks));
    fireEvent.click(screen.getByRole("button", { name: "Read label evidence" }));
    expect(screen.getByRole("alert").textContent).toContain("unavailable");
    expect(screen.queryByRole("article", { name: "Atlas link evidence" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Widget Makers Europe/ })).toBeNull();
  },
);
