import { expect, test } from "vitest";
import type { LineageView, OriginMatchRecord } from "../lib/lineage-api";
import { buildLineageGraph, provisionLabel, sliceGraph, visibleClaims } from "../lib/lineage-graph";
import { fixtureSemanticView, fixtureSupportedView, fixtureView } from "./lineage-fixture";

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
  expect(
    without({ kind: "semantic", similarity: 0.8, supports: [] }, { ...all, lexical: false }),
  ).toBe(0);
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
  expect(overview.claimIds).toHaveLength(1);
  expect(visibleClaims(graph, overview).map((claim) => claim.claimId)).toEqual(overview.claimIds);
  expect(visibleClaims(graph, focused).map((claim) => claim.claimId)).toEqual(["support:other"]);
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

test("a support needs both rendered edges through the same tabler", () => {
  const graph = buildLineageGraph(view, all);
  const starts = graph.edges.filter(
    (edge) => graph.nodes.get(edge.source)?.column === "organisation",
  );
  const finishes = graph.edges.filter((edge) => graph.nodes.get(edge.source)?.column === "tabler");
  const first = starts[0];
  const different = finishes.find((edge) => edge.source !== first?.target);
  if (first === undefined || different === undefined) {
    throw new Error("Need two coauthors");
  }
  const disconnected = { ...graph, edges: [first, different] };
  expect(sliceGraph(disconnected, null, 12).claimIds).toEqual([]);
  expect(visibleClaims(disconnected, sliceGraph(disconnected, null, 12))).toEqual([]);
  const complete = finishes.find((edge) => edge.source === first.target);
  if (complete === undefined) {
    throw new Error("Missing complete path");
  }
  expect(sliceGraph({ ...graph, edges: [first, complete] }, null, 12).claimIds).toHaveLength(1);
});

test("unknown author groups retain a complete supported path", () => {
  const graph = buildLineageGraph(
    { ...view, adoptions: [{ ...adoption, author_groups: [] }] },
    { ...all, tablers: "group" },
  );
  expect([...graph.nodes.values()].some((node) => node.label === "Group unknown")).toBe(true);
  expect(visibleClaims(graph, sliceGraph(graph, null, 12))).toHaveLength(1);
  expect(
    sliceGraph(buildLineageGraph(view, { ...all, lexical: false }), null, 12).claimIds,
  ).toEqual([]);
});

test("semantic paths use saved target supports and respect method switches", () => {
  const semanticView = fixtureSemanticView();
  const graph = buildLineageGraph(semanticView, { ...all, lexical: false });
  expect(graph.claims.size).toBeGreaterThan(0);
  expect([...graph.claims.values()].every((claim) => claim.origin.kind === "semantic")).toBe(true);
  expect(graph.edges.every((edge) => edge.semantic && !edge.lexical)).toBe(true);
  const combined = buildLineageGraph(semanticView, all);
  expect(combined.edges.some((edge) => edge.semantic && edge.lexical)).toBe(true);
  const lexical = buildLineageGraph(semanticView, { ...all, semantic: false });
  expect(lexical.edges.every((edge) => edge.lexical && !edge.semantic)).toBe(true);
  expect(
    buildLineageGraph(semanticView, { ...all, lexical: false, semantic: false }).edges,
  ).toEqual([]);
});

test.each(["verbatim", "semantic"] as const)(
  "focused shared edges retain only their %s method",
  (kind) => {
    const fixture = fixtureSemanticView();
    const lexical = fixture.origins.find(
      (item) => item.kind === "verbatim" && item.eligibility === "ask_first",
    );
    const semantic = fixture.origins.find(
      (item) => item.kind === "semantic" && item.eligibility === "ask_first",
    );
    if (lexical === undefined || semantic === undefined) {
      throw new Error("Missing mixed-method origins");
    }
    const graph = buildLineageGraph(
      { ...fixture, origins: [lexical, semantic] },
      { ...all, tablers: "group" },
    );
    const shared = graph.edges.find((edge) => edge.lexical && edge.semantic);
    const selected = kind === "verbatim" ? lexical : semantic;
    const organisation = [...graph.nodes.values()].find(
      (node) => node.column === "organisation" && node.label === selected.organisation,
    );
    if (shared === undefined || organisation === undefined) {
      throw new Error("Missing shared edge or selected organisation");
    }
    const incoming = graph.edges.find((edge) => edge.source === organisation.id);
    if (incoming === undefined) {
      throw new Error("Missing organisation edge");
    }
    for (const focus of [
      { kind: "node" as const, id: organisation.id },
      { kind: "edge" as const, id: incoming.id },
    ]) {
      const sliced = sliceGraph(graph, focus, 12);
      const retained = sliced.edges.find((edge) => edge.id === shared.id);
      expect(retained).toBeDefined();
      expect(retained?.claimIds).toEqual(incoming.claimIds);
      expect(retained?.lexical).toBe(kind === "verbatim");
      expect(retained?.semantic).toBe(kind === "semantic");
      expect(
        sliced.edges.every(
          (edge) =>
            edge.lexical === (kind === "verbatim") && edge.semantic === (kind === "semantic"),
        ),
      ).toBe(true);
    }
  },
);
