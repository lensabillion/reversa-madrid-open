import type { LineageView } from "./lineage-api";

/**
 * The lineage view as an explorable graph, in the brief's direction:
 * organisation (its submission) → who tabled the carrying amendment → final-act provision.
 *
 * Every edge carries the adopted phrases that support it, so a path is consistent: focusing
 * a node keeps only the edges that share its phrases, never an edge that merely touches a
 * neighbour. Only adopted wording that a named organisation's submission said before the
 * amendments is drawn (citations excluded): wording said later cannot have shaped them. Linear in the
 * origins times the authors and provisions of each phrase, plus sorting.
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
  phraseIds: readonly string[];
  /** Some supporting match is word for word / some is reworded and judged by Jev. */
  lexical: boolean;
  semantic: boolean;
}

export interface LineageGraph {
  nodes: ReadonlyMap<string, GraphNode>;
  edges: readonly GraphEdge[];
}

export interface GraphOptions {
  tablers: TablerLevel;
  /** Which methods' matches to draw. */
  lexical: boolean;
  semantic: boolean;
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
  const names = new Map(
    view.credits.filter((credit) => credit.holder_kind === "mep").map((c) => [c.holder_id, c.name]),
  );
  const phrases = new Map(view.adopted_phrases.map((phrase) => [phrase.phrase_id, phrase]));
  const adoptions = new Map<string, LineageView["adoptions"][number]>();
  for (const adoption of view.adoptions) {
    adoptions.set(adoption.amendment_id, adoption);
  }
  const nodes = new Map<string, GraphNode & { through: Set<string> }>();
  const edges = new Map<
    string,
    { source: string; target: string; phrases: Set<string> } & {
      lexical: boolean;
      semantic: boolean;
    }
  >();
  function node(
    id: string,
    column: GraphColumn,
    label: string,
    detail: string | null,
    phraseId: string,
  ) {
    const existing = nodes.get(id) ?? { id, column, label, detail, phrases: 0, through: new Set() };
    existing.through.add(phraseId);
    nodes.set(id, existing);
  }
  function edge(source: string, target: string, phraseId: string, semantic: boolean) {
    const id = `${source}→${target}`;
    const existing = edges.get(id) ?? {
      source,
      target,
      phrases: new Set<string>(),
      lexical: false,
      semantic: false,
    };
    existing.phrases.add(phraseId);
    existing.lexical ||= !semantic;
    existing.semantic ||= semantic;
    edges.set(id, existing);
  }
  for (const origin of view.origins) {
    const phrase = phrases.get(origin.phrase_id);
    const semantic = origin.kind === "semantic";
    if (
      phrase === undefined ||
      origin.is_citation ||
      origin.organisation === null ||
      origin.eligibility !== "ask_first" ||
      (semantic ? !options.semantic : !options.lexical)
    ) {
      continue;
    }
    const organisation = `org:${origin.actor_id ?? origin.organisation}`;
    node(organisation, "organisation", origin.organisation, null, phrase.phrase_id);
    const provisions = [...new Set(phrase.final_spans.map((span) => span.record_id))];
    for (const amendmentId of origin.amendment_ids) {
      const adoption = adoptions.get(amendmentId);
      if (adoption === undefined) {
        continue;
      }
      for (const tabler of tablersOf(adoption, options.tablers, names)) {
        node(tabler.id, "tabler", tabler.label, tabler.detail, phrase.phrase_id);
        edge(organisation, tabler.id, phrase.phrase_id, semantic);
        for (const recordId of provisions) {
          const provision = `prov:${recordId}`;
          node(provision, "provision", provisionLabel(recordId), null, phrase.phrase_id);
          edge(tabler.id, provision, phrase.phrase_id, semantic);
        }
      }
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
      phraseIds: [...value.phrases].sort(),
      lexical: value.lexical,
      semantic: value.semantic,
    })),
  };
}

export const graphColumns: readonly GraphColumn[] = ["organisation", "tabler", "provision"];

/** What the reader has clicked: a node, a line, or nothing (the overview). */
export type GraphFocus = { kind: "node"; id: string } | { kind: "edge"; id: string } | null;

export interface GraphSlice {
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
 * among them. With a focus: the edges sharing a phrase with it, restricted to those phrases,
 * and their nodes, still cut to `limit` per column so a hub stays readable.
 */
export function sliceGraph(graph: LineageGraph, focus: GraphFocus, limit: number): GraphSlice {
  let edges = graph.edges;
  let focusPhrases: Set<string> | null = null;
  if (focus !== null) {
    const touching =
      focus.kind === "edge"
        ? graph.edges.filter((edge) => edge.id === focus.id)
        : graph.edges.filter((edge) => edge.source === focus.id || edge.target === focus.id);
    focusPhrases = new Set(touching.flatMap((edge) => edge.phraseIds));
    const phrasesInFocus = focusPhrases;
    edges = graph.edges.flatMap((edge) => {
      const shared = edge.phraseIds.filter((id) => phrasesInFocus.has(id));
      return shared.length === 0 ? [] : [{ ...edge, phraseIds: shared }];
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
      for (const id of edge.phraseIds) {
        set.add(id);
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
    phraseIds: [...(focusPhrases ?? new Set(drawn.flatMap((edge) => edge.phraseIds)))].sort(),
  };
}
