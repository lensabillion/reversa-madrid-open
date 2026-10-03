// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { AtlasCoverageBadges, AtlasModes } from "../components/atlas-coverage";
import type { AtlasLayerCoverage } from "../lib/atlas-api";

afterEach(cleanup);

const layer = (fields: Partial<AtlasLayerCoverage>): AtlasLayerCoverage => ({
  layer: "metadata",
  status: "complete",
  count: 1,
  reason: null,
  source_updated_on: null,
  ...fields,
});

function badges(): (string | null)[] {
  return screen.getAllByRole("listitem").map((item) => item.textContent);
}

test("one badge per layer shows its count, its status and the reason unless complete", () => {
  render(
    <AtlasCoverageBadges
      coverage={[
        layer({ layer: "committee_amendments", count: 4852 }),
        layer({ layer: "asks", status: "partial", count: 304, reason: "45 attachments failed" }),
        layer({ layer: "plenary_amendments", status: "missing", count: 0, reason: "None tabled" }),
        layer({ layer: "votes", status: "stale", count: 12, reason: "Source stopped in 2024" }),
        layer({ layer: "final_act", status: "not_applicable", count: null, reason: "File open" }),
        layer({ layer: "meetings", status: "not_collected", count: null, reason: null }),
      ]}
    />,
  );
  expect(screen.getByRole("list", { name: "Source layers" })).toBeDefined();
  expect(badges()).toEqual([
    "Committee amendments4,852Complete",
    "Asks304Partial45 attachments failed",
    "Plenary amendments0Missing from the sourceNone tabled",
    "Votes12StaleSource stopped in 2024",
    "Final actnot countedNot applicableFile open",
    "Meetingsnot countedNot collected in this runNo reason was recorded.",
  ]);
});

test("an uncounted layer never reads as zero, and a counted zero stays a zero", () => {
  render(
    <AtlasCoverageBadges
      coverage={[
        layer({ layer: "meetings", status: "not_collected", count: null, reason: "No connector" }),
        layer({ layer: "plenary_amendments", status: "missing", count: 0, reason: "None tabled" }),
      ]}
    />,
  );
  const [uncounted, zero] = badges();
  expect(uncounted).toContain("not counted");
  expect(uncounted).not.toMatch(/\d/);
  expect(zero).toContain("Plenary amendments0");
  expect(zero).not.toContain("not counted");
});

test("a complete layer hides a stray reason, and a run without layers says coverage is unknown", () => {
  render(<AtlasCoverageBadges coverage={[layer({ reason: "ignored" })]} />);
  expect(badges()).toEqual(["Metadata1Complete"]);
  cleanup();
  render(<AtlasCoverageBadges coverage={[]} />);
  expect(screen.getByText("Coverage unknown: this run recorded no source layers.")).toBeDefined();
  expect(screen.queryByRole("list")).toBeNull();
});

test("mode labels are listed verbatim, and no list is drawn without them", () => {
  render(<AtlasModes modes={["Contextual evidence, not textual", "Negotiation in progress"]} />);
  expect(screen.getByRole("list", { name: "Result modes" })).toBeDefined();
  expect(badges()).toEqual(["Contextual evidence, not textual", "Negotiation in progress"]);
  cleanup();
  const { container } = render(<AtlasModes modes={[]} />);
  expect(container.textContent).toBe("");
  expect(screen.queryByRole("list")).toBeNull();
});
