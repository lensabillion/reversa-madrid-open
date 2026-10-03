// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AtlasExplorer } from "../components/atlas-explorer";
import type { AtlasGraphSnapshot } from "../components/atlas-graph";
import { AtlasWorkspace } from "../components/atlas-workspace";
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

function workspace(suppliedLinks = links) {
  return (
    <AtlasWorkspace
      snapshot={snapshot}
      links={suppliedLinks}
      coverage={[]}
      coverageNotes={["Synthetic source coverage"]}
      dataNotice={notice}
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
