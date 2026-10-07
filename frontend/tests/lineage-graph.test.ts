import { expect, test } from "vitest";
import type { LineageView, OriginMatchRecord } from "../lib/lineage-api";
import { buildLineageGraph, provisionLabel, sliceGraph } from "../lib/lineage-graph";
import { fixtureSupportedView, fixtureView } from "./lineage-fixture";

const view = fixtureSupportedView();
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
  expect(without({ kind: "semantic", similarity: 0.8 }, { ...all, lexical: false })).toBe(0);
});

test("focus keeps only paths through the node, and the overview cuts each column", () => {
  const second = phrase.phrase_id;
  const evidence = adoption.evidence?.[0];
  const support = origin.supports?.[0];
  if (evidence === undefined || support === undefined) {
    throw new Error("Missing supports");
  }
  const originalFinal = phrase.final_spans[0];
  if (originalFinal === undefined) {
    throw new Error("Missing final occurrence");
  }
  const finalSpan = { ...originalFinal, record_id: "art:32024R1689:article-13" };
  if (finalSpan.start === undefined) {
    throw new Error("Missing final occurrence");
  }
  const other: LineageView = {
    ...view,
    adopted_phrases: [{ ...phrase, final_spans: [...phrase.final_spans, finalSpan] }],
    adoptions: [
      ...view.adoptions,
      {
        ...adoption,
        amendment_id: "am:other",
        author_ids: ["actor:mep:1"],
        author_names: ["Other Member"],
        author_groups: ["EPP"],
        phrase_ids: [second],
        evidence: [
          {
            ...evidence,
            evidence_id: "evidence:other",
            amendment_span: { ...evidence.amendment_span, record_id: "am:other" },
            final_span: { ...evidence.final_span, record_id: finalSpan.record_id },
          },
        ],
      },
    ],
    origins: [
      origin,
      {
        ...origin,
        phrase_id: second,
        organisation: "Beta Association",
        actor_id: null,
        document_id: "doc:other",
        span: { ...origin.span, record_id: "doc:other" },
        amendment_ids: [adoption.amendment_id, "am:other"],
        supports: [
          {
            ...support,
            support_id: "support:other",
            adoption_evidence_id: "evidence:other",
            amendment_id: "am:other",
            submission_span: { ...support.submission_span, record_id: "doc:other" },
            amendment_span: { ...support.amendment_span, record_id: "am:other" },
            final_span: { ...support.final_span, record_id: finalSpan.record_id },
          },
        ],
      },
    ],
  };
  const graph = buildLineageGraph(other, all);
  const beta = [...graph.nodes.values()].find((node) => node.label === "Beta Association");
  if (beta === undefined) {
    throw new Error("Beta Association missing");
  }
  expect(graph.claims.size).toBe(2);
  const acme = [...graph.nodes.values()].find((node) => node.label === origin.organisation);
  if (acme === undefined) {
    throw new Error("Missing Acme");
  }
  const acmeSlice = sliceGraph(graph, { kind: "node", id: acme.id }, 12);
  expect(acmeSlice.columns.provision.shown.map((node) => node.label)).toEqual(["Art. 12"]);
  const focused = sliceGraph(graph, { kind: "node", id: beta.id }, 12);
  expect(focused.phraseIds).toEqual([second]);
  expect(focused.claimIds).toEqual(["support:other"]);
  expect(focused.columns.provision.shown.map((node) => node.label)).toEqual(["Art. 13"]);
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

test("coauthors share one support claim and legacy views remain unavailable", () => {
  const graph = buildLineageGraph(view, all);
  expect(graph.claims.size).toBe(1);
  expect(new Set(graph.edges.flatMap((edge) => edge.claimIds)).size).toBe(1);
  expect(graph.edges).toHaveLength(4);
  const legacy = buildLineageGraph(fixtureView(), all);
  expect(legacy.unavailableReason).toContain("carrier-specific");
  expect(legacy.edges).toEqual([]);
});
