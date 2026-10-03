import { expect, test } from "vitest";
import type { LineageView, OriginMatchRecord } from "../lib/lineage-api";
import { buildLineageGraph, provisionLabel, sliceGraph } from "../lib/lineage-graph";
import { fixtureView } from "./lineage-fixture";

const view = fixtureView();
const [origin] = view.origins;
const [adoption] = view.adoptions;
const [phrase] = view.adopted_phrases;
if (origin === undefined || adoption === undefined || phrase === undefined) {
  throw new Error("The lineage fixture lost its records");
}
const all = { tablers: "member" as const, lexical: true, semantic: true };

test("provision records read as the law cites them", () => {
  expect(provisionLabel("art:32024R1689:article-99-11")).toBe("Art. 99(11)");
  expect(provisionLabel("art:32024R1689:recital-3")).toBe("Recital 3");
  expect(provisionLabel("art:32024R1689:annex-iii")).toBe("Annex III");
  expect(provisionLabel("art:32024R1689:preamble")).toBe("preamble");
});

test("an origin draws organisation → each tabler → each provision, carrying its phrase", () => {
  const graph = buildLineageGraph(view, all);
  const columns = [...graph.nodes.values()].map((node) => [node.column, node.label]);
  expect(columns).toContainEqual(["organisation", "Acme Unknown Lobby"]);
  expect(columns.filter(([column]) => column === "tabler")).toHaveLength(
    adoption.author_ids.length,
  );
  expect(graph.edges.every((edge) => edge.phraseIds.includes(phrase.phrase_id))).toBe(true);
  expect(graph.edges.every((edge) => edge.lexical && !edge.semantic)).toBe(true);
  const grouped = buildLineageGraph(view, { ...all, tablers: "group" });
  expect(
    [...grouped.nodes.values()].filter((n) => n.column === "tabler").map((n) => n.label),
  ).toEqual(["S&D"]);
});

test("later, citing, unnamed and switched-off matches draw nothing", () => {
  const without = (changes: Partial<OriginMatchRecord>, options = all) =>
    buildLineageGraph(
      { ...view, origins: [{ ...origin, ...changes }] } satisfies LineageView,
      options,
    ).edges.length;
  expect(without({ eligibility: "amendment_first", precedes: false })).toBe(0);
  expect(without({ is_citation: true })).toBe(0);
  expect(without({ organisation: null })).toBe(0);
  expect(without({}, { ...all, lexical: false })).toBe(0);
  expect(
    without({ kind: "semantic", similarity: 0.8 }, { ...all, lexical: false }),
  ).toBeGreaterThan(0);
});

test("focus keeps only paths through the node, and the overview cuts each column", () => {
  const second = "phrase:00000000000000aa";
  const other: LineageView = {
    ...view,
    adopted_phrases: [...view.adopted_phrases, { ...phrase, phrase_id: second }],
    adoptions: [
      ...view.adoptions,
      {
        ...adoption,
        amendment_id: "am:other",
        author_ids: ["actor:mep:1"],
        author_names: ["Other Member"],
        author_groups: ["EPP"],
        phrase_ids: [second],
      },
    ],
    origins: [
      origin,
      {
        ...origin,
        phrase_id: second,
        organisation: "Beta Association",
        actor_id: null,
        amendment_ids: ["am:other"],
      },
    ],
  };
  const graph = buildLineageGraph(other, all);
  const beta = [...graph.nodes.values()].find((node) => node.label === "Beta Association");
  if (beta === undefined) {
    throw new Error("Beta Association missing");
  }
  const focused = sliceGraph(graph, { kind: "node", id: beta.id }, 12);
  expect(focused.phraseIds).toEqual([second]);
  expect(focused.columns.organisation.shown.map((node) => node.label)).toEqual([
    "Beta Association",
  ]);
  expect(focused.columns.tabler.shown.map((node) => node.label)).toEqual(["Other Member"]);
  expect(focused.edges.every((edge) => edge.phraseIds.every((id) => id === second))).toBe(true);
  const overview = sliceGraph(graph, null, 1);
  expect(overview.columns.organisation.shown).toHaveLength(1);
  expect(overview.columns.organisation.hidden).toBe(1);
  const [edge] = graph.edges;
  if (edge === undefined) {
    throw new Error("No edge");
  }
  expect(sliceGraph(graph, { kind: "edge", id: edge.id }, 12).phraseIds).toEqual(edge.phraseIds);
});
