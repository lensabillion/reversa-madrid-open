import { collectSupportedClaims, type SupportedLineageClaim } from "./lineage";
import type { LineageView } from "./lineage-api";

/**
 * The lineage view as an explorable graph, in the brief's direction:
 * organisation (its submission) → who tabled the carrying amendment → final-act provision.
 *
 * Every edge carries the saved support IDs that establish its exact carrier path, so a path is consistent: focusing
 * a node keeps only the edges that share those support IDs, never an edge that merely touches a
 * neighbour. Only adopted wording that a named organisation's submission said before the
 * amendments is drawn (citations excluded): wording said later cannot have shaped them. Linear in saved supports times the number of carrier authors, plus sorting.
 */

export type GraphColumn = "organisation" | "tabler" | "provision";
/** Draw Members one by one, or fold them into their political groups to cut the lines. */
export type TablerLevel = "member" | "group";

export interface GraphNode {
  id: string;
  column: GraphColumn;
  label: string;
  /** A second line: the political group of a Member, or the provision's record. */
  detail: string | null;
  /** Distinct phrases through this node; the size used to order and cut each column. */
  phrases: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  claimIds: readonly string[];
  /** Phrase IDs are display context, never graph join identity. */
  phraseIds: readonly string[];
  /** Some supporting match is word for word / some is reworded and judged by Jev. */
  lexical: boolean;
  semantic: boolean;
}

export interface LineageGraph {
  nodes: ReadonlyMap<string, GraphNode>;
  edges: readonly GraphEdge[];
  claims: ReadonlyMap<string, SupportedLineageClaim>;
  unavailableReason: string | null;
  unsupportedOrigins: number;
}

export interface GraphOptions {
  tablers: TablerLevel;
  /** Which methods' matches to draw. */
  lexical: boolean;
  semantic: boolean;
}

export interface GraphScope extends GraphOptions {
  focus: GraphFocus;
  limit: number;
}

/** `art:32024R1689:article-99-11` → `Art. 99(11)`; `recital-3` → `Recital 3`. */
export function provisionLabel(recordId: string): string {
  const local = recordId.split(":").at(-1) ?? recordId;
  const [kind, number, ...rest] = local.split("-");
  const tail = rest.map((part) => `(${part})`).join("");
  switch (kind) {
    case "article":
      return `Art. ${number ?? ""}${tail}`;
    case "recital":
      return `Recital ${number ?? ""}${tail}`;
    case "annex":
      return `Annex ${(number ?? "").toUpperCase()}${tail}`;
    default:
      return local;
  }
}

interface Tabler {
  id: string;
  label: string;
  detail: string | null;
}

/** The tablers of one amendment at the chosen level; an authorless amendment is its body's text. */
function tablersOf(
  adoption: LineageView["adoptions"][number],
  level: TablerLevel,
  names: ReadonlyMap<string, string>,
): Tabler[] {
  if (adoption.author_ids.length === 0) {
    const body = adoption.committee ?? adoption.stage;
    const named = adoption.author_names.map((name) => ({
      id: `tabler:name:${name}`,
      label: name,
      detail: null,
    }));
    if (level === "member" && named.length > 0) {
      return named;
    }
    return [{ id: `tabler:text:${body}`, label: `${body} text, no Member named`, detail: null }];
  }
  if (level === "group") {
    const groups = new Set(adoption.author_groups.map((group) => group ?? "Group unknown"));
    if (groups.size === 0) {
      groups.add("Group unknown");
    }
    return [...groups].map((group) => ({
      id: `tabler:group:${group}`,
      label: group,
      detail: null,
    }));
  }
  return adoption.author_ids.map((authorId, index) => ({
    id: `tabler:${authorId}`,
    label: names.get(authorId) ?? adoption.author_names[index] ?? authorId,
    detail: adoption.author_groups[index] ?? null,
  }));
}

/** Builds the whole graph; the component cuts and focuses it for display. */
export function buildLineageGraph(view: LineageView, options: GraphOptions): LineageGraph {
  const supported = collectSupportedClaims(view);
  const claims = new Map(
    supported.claims
      .filter((claim) => (claim.origin.kind === "semantic" ? options.semantic : options.lexical))
      .map((claim) => [claim.claimId, claim]),
  );
  const names = new Map(
    view.credits
      .filter((credit) => credit.holder_kind === "mep")
      .map((credit) => [credit.holder_id, credit.name]),
  );
  const nodes = new Map<string, GraphNode & { through: Set<string> }>();
  const edges = new Map<string, { source: string; target: string; claims: Set<string> }>();
  function node(
    id: string,
    column: GraphColumn,
    label: string,
    detail: string | null,
    phraseId: string,
  ) {
    const existing = nodes.get(id) ?? {
      id,
      column,
      label,
      detail,
      phrases: 0,
      through: new Set<string>(),
    };
    existing.through.add(phraseId);
    nodes.set(id, existing);
  }
  function edge(source: string, target: string, claimId: string) {
    const id = `${source}→${target}`;
    const existing = edges.get(id) ?? { source, target, claims: new Set<string>() };
    existing.claims.add(claimId);
    edges.set(id, existing);
  }
  for (const claim of claims.values()) {
    const name = claim.origin.organisation;
    if (name === null) {
      throw new Error(`Supported association has no named organisation: ${claim.claimId}`);
    }
    const organisation = `org:${claim.origin.actor_id ?? name}`;
    const recordId = claim.support.final_span.record_id;
    const provision = `prov:${recordId}`;
    node(organisation, "organisation", name, null, claim.phraseId);
    node(provision, "provision", provisionLabel(recordId), null, claim.phraseId);
    for (const tabler of tablersOf(claim.adoption, options.tablers, names)) {
      node(tabler.id, "tabler", tabler.label, tabler.detail, claim.phraseId);
      edge(organisation, tabler.id, claim.claimId);
      edge(tabler.id, provision, claim.claimId);
    }
  }
  return {
    nodes: new Map(
      [...nodes.values()].map(({ through, ...rest }) => [
        rest.id,
        { ...rest, phrases: through.size },
      ]),
    ),
    edges: [...edges.entries()].map(([id, value]) => ({
      id,
      source: value.source,
      target: value.target,
      claimIds: [...value.claims].sort(),
      phraseIds: [
        ...new Set(
          [...value.claims].flatMap((claimId) => {
            const claim = claims.get(claimId);
            return claim === undefined ? [] : [claim.phraseId];
          }),
        ),
      ].sort(),
      lexical: [...value.claims].some((id) => claims.get(id)?.origin.kind === "verbatim"),
      semantic: [...value.claims].some((id) => claims.get(id)?.origin.kind === "semantic"),
    })),
    claims,
    unavailableReason: supported.unavailableReason,
    unsupportedOrigins: supported.unsupportedOrigins,
  };
}

export const graphColumns: readonly GraphColumn[] = ["organisation", "tabler", "provision"];

/** What the reader has clicked: a node, a line, or nothing (the overview). */
export type GraphFocus = { kind: "node"; id: string } | { kind: "edge"; id: string } | null;

export interface GraphSlice {
  claimIds: readonly string[];
  /** Shown nodes per column, largest first, and how many more the column holds. */
  columns: Record<GraphColumn, { shown: readonly GraphNode[]; hidden: number }>;
  edges: readonly GraphEdge[];
  /** Phrases behind the focus (all phrases of the drawn edges in the overview). */
  phraseIds: readonly string[];
}

function byWeight(left: GraphNode, right: GraphNode): number {
  return right.phrases - left.phrases || left.label.localeCompare(right.label);
}

/**
 * What to draw. Without a focus: the `limit` heaviest nodes of each column and the edges
 * among them. With a focus: the edges sharing a support with it, restricted to those supports,
 * and their nodes, still cut to `limit` per column so a hub stays readable.
 */
export function sliceGraph(graph: LineageGraph, focus: GraphFocus, limit: number): GraphSlice {
  let edges = graph.edges;
  let focusClaims: Set<string> | null = null;
  if (focus !== null) {
    const touching =
      focus.kind === "edge"
        ? graph.edges.filter((edge) => edge.id === focus.id)
        : graph.edges.filter((edge) => edge.source === focus.id || edge.target === focus.id);
    focusClaims = new Set(touching.flatMap((edge) => edge.claimIds));
    const claimsInFocus = focusClaims;
    edges = graph.edges.flatMap((edge) => {
      const shared = edge.claimIds.filter((id) => claimsInFocus.has(id));
      return shared.length === 0
        ? []
        : [
            {
              ...edge,
              claimIds: shared,
              phraseIds: [
                ...new Set(
                  shared.flatMap((id) => {
                    const claim = graph.claims.get(id);
                    return claim === undefined ? [] : [claim.phraseId];
                  }),
                ),
              ].sort(),
              lexical: shared.some((id) => graph.claims.get(id)?.origin.kind === "verbatim"),
              semantic: shared.some((id) => graph.claims.get(id)?.origin.kind === "semantic"),
            },
          ];
    });
    if (focus.kind === "node") {
      // Keep paths through the focused node: on its own column, only itself.
      const column = graph.nodes.get(focus.id)?.column;
      edges = edges.filter((edge) => {
        const ends = [graph.nodes.get(edge.source), graph.nodes.get(edge.target)];
        return ends.every(
          (end) => end === undefined || end.column !== column || end.id === focus.id,
        );
      });
    }
  }
  const weights = new Map<string, Set<string>>();
  for (const edge of edges) {
    for (const end of [edge.source, edge.target]) {
      const set = weights.get(end) ?? new Set<string>();
      for (const id of edge.claimIds) {
        const claim = graph.claims.get(id);
        if (claim !== undefined) {
          set.add(claim.phraseId);
        }
      }
      weights.set(end, set);
    }
  }
  const candidates = [...graph.nodes.values()]
    .filter((node) => focus === null || weights.has(node.id))
    .map((node) =>
      focus === null ? node : { ...node, phrases: weights.get(node.id)?.size ?? node.phrases },
    );
  const pinned = focus?.kind === "node" ? focus.id : null;
  function cut(column: GraphColumn): { shown: readonly GraphNode[]; hidden: number } {
    const all = candidates.filter((node) => node.column === column).sort(byWeight);
    const shown = all.slice(0, limit);
    const pinnedNode = all.find((node) => node.id === pinned);
    if (pinnedNode !== undefined && !shown.includes(pinnedNode)) {
      shown.splice(shown.length - 1, 1, pinnedNode);
    }
    return { shown, hidden: all.length - shown.length };
  }
  const columns: Record<GraphColumn, { shown: readonly GraphNode[]; hidden: number }> = {
    organisation: cut("organisation"),
    tabler: cut("tabler"),
    provision: cut("provision"),
  };
  const visible = new Set(graphColumns.flatMap((column) => columns[column].shown.map((n) => n.id)));
  const drawn = edges.filter((edge) => visible.has(edge.source) && visible.has(edge.target));
  return {
    columns,
    edges: drawn,
    claimIds: completeRenderedClaims(graph, drawn),
    phraseIds: [
      ...new Set(
        drawn
          .flatMap((edge) => edge.claimIds)
          .flatMap((id) => {
            const claim = graph.claims.get(id);
            return claim === undefined ? [] : [claim.phraseId];
          }),
      ),
    ].sort(),
  };
}

/**
 * A claim is visible only if both edges of its path survive the scope and clipping,
 * through the same tabler. Linear in rendered edge/support memberships plus
 * O(n log n) sorting of visible support IDs; bounded by one saved law view.
 */
function completeRenderedClaims(graph: LineageGraph, edges: readonly GraphEdge[]): string[] {
  const starts = new Map<string, Set<string>>();
  const finishes = new Map<string, Set<string>>();
  for (const edge of edges) {
    const source = graph.nodes.get(edge.source)?.column;
    const target = graph.nodes.get(edge.target)?.column;
    const matches =
      source === "organisation" && target === "tabler"
        ? starts
        : source === "tabler" && target === "provision"
          ? finishes
          : null;
    if (matches === null) {
      continue;
    }
    const tabler = source === "tabler" ? edge.source : edge.target;
    for (const id of edge.claimIds) {
      const seen = matches.get(id) ?? new Set<string>();
      seen.add(tabler);
      matches.set(id, seen);
    }
  }
  return [...starts]
    .filter(([id, tablers]) => [...tablers].some((tabler) => finishes.get(id)?.has(tabler)))
    .map(([id]) => id)
    .sort();
}

/** The graph and sample both consume this exact rendered-path selection. */
export function visibleClaims(
  graph: LineageGraph,
  slice: GraphSlice,
): readonly SupportedLineageClaim[] {
  return slice.claimIds.flatMap((id) => {
    const claim = graph.claims.get(id);
    return claim === undefined ? [] : [claim];
  });
}

export function describeGraphScope(scope: GraphScope, graph: LineageGraph): string {
  const methods =
    [scope.lexical ? "lexical" : null, scope.semantic ? "semantic" : null]
      .filter((method) => method !== null)
      .join(" + ") || "no methods";
  const focus =
    scope.focus === null
      ? "overview"
      : scope.focus.kind === "node"
        ? (graph.nodes.get(scope.focus.id)?.label ?? scope.focus.id)
        : scope.focus.id;
  return `${methods} · ${scope.tablers === "group" ? "political groups" : "Members"} · ${focus} · up to ${scope.limit} nodes per column`;
}
