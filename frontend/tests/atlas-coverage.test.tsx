// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { AtlasWorkspace } from "../components/atlas-workspace";
import { type AtlasBundle, atlasLinkViews } from "../lib/atlas";
import type { AtlasLayerCoverage, AtlasLayerStatus } from "../lib/atlas-api";

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
const allLinks = atlasLinkViews(bundle);
// What the backend sends when nothing passed: audit candidates only.
const auditOnly = allLinks.filter(
  (link) =>
    link.evidence.assessment.status === "unconfirmed" ||
    link.evidence.assessment.status === "contradicted",
);
const tls =
  "Have Your Say could not be reached: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed";

function row(
  layer: AtlasLayerCoverage["layer"],
  status: AtlasLayerStatus,
  count: number | null,
  reason: string | null = null,
): AtlasLayerCoverage {
  return { layer, status, count, reason, source_updated_on: null };
}
const collected: AtlasLayerCoverage[] = [
  row("metadata", "complete", 1),
  row("committee_amendments", "complete", 4852),
  row("plenary_amendments", "complete", 312),
  row("asks", "complete", 140),
  row("votes", "not_collected", null, "Connector not built"),
];

function renderWorkspace(
  coverage: readonly AtlasLayerCoverage[],
  links: typeof allLinks = allLinks,
) {
  render(
    <AtlasWorkspace
      snapshot={{ snapshot_id: "coverage-test", nodes: [], edges: [] }}
      links={links}
      coverage={coverage}
      coverageNotes={["Synthetic source coverage"]}
      dataNotice="Invented contract fixtures only."
      analysis={<p>Supplied outcome table</p>}
    />,
  );
  return screen.getByRole("region", { name: "Source layers" });
}

function badges(layers: HTMLElement): string[] {
  return within(layers)
    .getAllByRole("listitem")
    .map((item) => item.textContent ?? "");
}

afterEach(cleanup);

test.each([
  {
    status: "complete",
    count: 4852,
    reason: null,
    text: "Committee amendments · complete · 4,852",
  },
  {
    status: "partial",
    count: 3,
    reason: "2 of 5 attachments failed",
    text: "Committee amendments · partial · 3Reason: 2 of 5 attachments failed",
  },
  {
    status: "stale",
    count: 1,
    reason: "The dump ends early",
    text: "Committee amendments · stale · 1Reason: The dump ends early",
  },
  {
    status: "missing",
    count: 0,
    reason: tls,
    text: `Committee amendments · missing · 0Reason: ${tls}`,
  },
  {
    status: "not_collected",
    count: null,
    reason: "Connector not built",
    text: "Committee amendments · not collectedReason: Connector not built",
  },
  {
    status: "not_applicable",
    count: null,
    reason: "No plenary stage",
    text: "Committee amendments · not applicableReason: No plenary stage",
  },
] satisfies {
  status: AtlasLayerStatus;
  count: number | null;
  reason: string | null;
  text: string;
}[])(
  "the opening graph view shows a $status layer's badge and reason",
  ({ status, count, reason, text }) => {
    const layers = renderWorkspace([row("committee_amendments", status, count, reason)]);
    expect(
      screen.getByRole("button", { name: "Explore the graph" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(badges(layers)).toEqual([text]);
  },
);

test("every coverage row gets one badge, in the supplied order", () => {
  const layers = renderWorkspace(collected);
  expect(badges(layers)).toEqual([
    "Procedure metadata · complete · 1",
    "Committee amendments · complete · 4,852",
    "Plenary amendments · complete · 312",
    "Consultation feedback · complete · 140",
    "Votes · not collectedReason: Connector not built",
  ]);
  // Published links exist, so no empty-graph explanation is shown.
  expect(within(layers).queryByText(/no link was published|No links can be shown/)).toBeNull();
});

test("a failed consultation collection says the links are missing data, not absent influence", () => {
  const layers = renderWorkspace(
    collected.map((item) => (item.layer === "asks" ? row("asks", "missing", 0, `${tls}.`) : item)),
    [],
  );
  expect(
    within(layers).getByText(
      `No links can be shown because consultation feedback is missing: ${tls}.`,
    ),
  ).toBeDefined();
  expect(within(layers).queryByText(/none met the publication bar/)).toBeNull();
});

test("an absent consultation layer and two absent amendment layers are all named", () => {
  const layers = renderWorkspace(
    [
      row("committee_amendments", "not_collected", null, "Parltrack dump unavailable"),
      row("plenary_amendments", "not_applicable", null, "No plenary stage"),
    ],
    [],
  );
  expect(
    within(layers).getByText(
      "No links can be shown because consultation feedback has no coverage record; and committee amendments was not collected: Parltrack dump unavailable; and plenary amendments does not apply to this law: No plenary stage.",
    ),
  ).toBeDefined();
});

test("collected layers with no published link say how many candidates failed the bar", () => {
  const layers = renderWorkspace(collected, auditOnly);
  expect(auditOnly).toHaveLength(3);
  expect(
    within(layers).getByText(
      "Consultation feedback and amendments were collected, but no link was published. 3 candidate links were checked and kept for audit as unconfirmed or contradicted; none met the publication bar. Candidates with insufficient evidence are not counted.",
    ),
  ).toBeDefined();
});

test("one missing amendment layer is not a blocker, but incomplete inputs are flagged", () => {
  const layers = renderWorkspace(
    [
      row("committee_amendments", "complete", 2),
      row("plenary_amendments", "missing", 0, "None were tabled"),
      row("asks", "partial", 5, "1 of 5 submissions failed"),
    ],
    [],
  );
  expect(
    within(layers).getByText(
      "Consultation feedback and amendments were collected, but no link was published. No candidate link reached the audit view, so none met the publication bar. Candidates with insufficient evidence are not counted. Some of those layers are incomplete; see their badges.",
    ),
  ).toBeDefined();
});

test("a run with no coverage rows says so instead of showing an empty badge list", () => {
  const layers = renderWorkspace([]);
  expect(within(layers).getByText("This run recorded no source coverage.")).toBeDefined();
  expect(within(layers).queryByRole("list")).toBeNull();
});
