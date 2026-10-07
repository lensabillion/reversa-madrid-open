"use client";

import { type ReactNode, useMemo, useState } from "react";
import type { LineagePhraseRow } from "../lib/lineage";
import type { LineageView } from "../lib/lineage-api";
import {
  buildLineageGraph,
  type GraphColumn,
  type GraphEdge,
  type GraphFocus,
  type GraphNode,
  graphColumns,
  sliceGraph,
  type TablerLevel,
} from "../lib/lineage-graph";
import { KindLegend } from "./lineage-kind";
import { retryStyle } from "./view-state";

const count = new Intl.NumberFormat("en-US");
/** Nodes per column before "show more": enough to read a hub, few enough to read its lines. */
export const GRAPH_NODES_PER_COLUMN = 12;
const PHRASES_SHOWN = 5;

const columnTitle: Record<GraphColumn, string> = {
  organisation: "Organisation (its submission)",
  tabler: "Tabled the amendment",
  provision: "Provision of the final act",
};
const VIEW_WIDTH = 1100;
const NODE_WIDTH = 270;
const ROW = 34;
const TOP = 30;
const columnX: Record<GraphColumn, number> = { organisation: 0, tabler: 415, provision: 830 };
// Teal lexical, violet semantic: the same pair as `lineage-kind.tsx`.
const TEAL = "#0d9488";
const VIOLET = "#7c3aed";

function clip(text: string, length: number): string {
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

interface Placed {
  node: GraphNode;
  x: number;
  y: number;
}

function EdgePath({
  edge,
  from,
  to,
  max,
  lit,
  dim,
  selected,
  onSelect,
}: {
  edge: GraphEdge;
  from: Placed;
  to: Placed;
  max: number;
  lit: boolean;
  dim: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const x1 = from.x + NODE_WIDTH;
  const y1 = from.y + ROW / 2 - 3;
  const x2 = to.x;
  const y2 = to.y + ROW / 2 - 3;
  const middle = (x1 + x2) / 2;
  const d = `M${x1},${y1} C${middle},${y1} ${middle},${y2} ${x2},${y2}`;
  const width = 1.2 + 5 * Math.sqrt(edge.phraseIds.length / Math.max(1, max));
  const opacity = selected || lit ? 0.9 : dim ? 0.08 : 0.35;
  const label = `${count.format(edge.phraseIds.length)} phrases, ${edge.lexical ? "lexical" : ""}${edge.lexical && edge.semantic ? " and " : ""}${edge.semantic ? "semantic" : ""}`;
  return (
    <g>
      {edge.lexical && (
        <path d={d} fill="none" stroke={TEAL} strokeWidth={width} strokeOpacity={opacity} />
      )}
      {edge.semantic && (
        <path
          d={d}
          fill="none"
          stroke={VIOLET}
          strokeWidth={edge.lexical ? 1.6 : width}
          strokeDasharray="6 4"
          strokeOpacity={Math.min(1, opacity + 0.2)}
        />
      )}
      {/* biome-ignore lint/a11y/useSemanticElements: an SVG path cannot be a <button>. */}
      <path
        d={d}
        fill="none"
        stroke="transparent"
        strokeWidth={Math.max(12, width + 6)}
        className="cursor-pointer"
        role="button"
        tabIndex={-1}
        aria-label={`Line: ${label}`}
        onClick={onSelect}
      >
        <title>{label}</title>
      </path>
    </g>
  );
}

function NodeBox({
  placed,
  selected,
  onSelect,
  onHover,
}: {
  placed: Placed;
  selected: boolean;
  onSelect: () => void;
  onHover: (id: string | null) => void;
}) {
  const { node, x, y } = placed;
  const name = node.detail === null ? node.label : `${node.label} (${node.detail})`;
  return (
    // biome-ignore lint/a11y/useSemanticElements: an SVG group cannot be a <button>.
    <g
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`${name}: ${count.format(node.phrases)} phrases`}
      className="cursor-pointer focus-visible:outline-none"
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      onMouseEnter={() => onHover(node.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(node.id)}
      onBlur={() => onHover(null)}
    >
      <title>{name}</title>
      <rect
        x={x}
        y={y}
        width={NODE_WIDTH}
        height={ROW - 6}
        rx={3}
        fill={selected ? "#134e4a" : "#ffffff"}
        stroke={selected ? "#134e4a" : "#d6d3d1"}
      />
      <text
        x={x + 10}
        y={y + 18}
        fontSize={12.5}
        fill={selected ? "#ffffff" : "#1c1917"}
        className="select-none"
      >
        {clip(name, 34)}
      </text>
      <text
        x={x + NODE_WIDTH - 10}
        y={y + 18}
        fontSize={11.5}
        textAnchor="end"
        fill={selected ? "#ccfbf1" : "#78716c"}
        className="select-none tabular-nums"
      >
        {count.format(node.phrases)}
      </text>
    </g>
  );
}

/**
 * The lineage as a clickable graph: organisation → who tabled → final-act provision. The
 * overview draws only the heaviest nodes of each column; clicking a node or a line focuses
 * the paths through it (only the phrases they share) and lists that evidence below.
 */
export function LineageGraphExplorer({
  view,
  phrases,
  renderPhrase,
}: {
  view: LineageView;
  phrases: readonly LineagePhraseRow[];
  renderPhrase: (phrase: LineagePhraseRow) => ReactNode;
}) {
  const [tablers, setTablers] = useState<TablerLevel>("group");
  const [lexical, setLexical] = useState(true);
  const [semantic, setSemantic] = useState(true);
  const [focus, setFocus] = useState<GraphFocus>(null);
  const [limit, setLimit] = useState(GRAPH_NODES_PER_COLUMN);
  const [hover, setHover] = useState<string | null>(null);
  const [shownPhrases, setShownPhrases] = useState(PHRASES_SHOWN);
  const [query, setQuery] = useState("");

  const graph = useMemo(
    () => buildLineageGraph(view, { tablers, lexical, semantic }),
    [view, tablers, lexical, semantic],
  );
  const slice = useMemo(() => sliceGraph(graph, focus, limit), [graph, focus, limit]);
  const byId = useMemo(() => new Map(phrases.map((row) => [row.phraseId, row])), [phrases]);

  function choose(next: GraphFocus) {
    setFocus(next);
    setShownPhrases(PHRASES_SHOWN);
  }

  const placed = new Map<string, Placed>();
  for (const column of graphColumns) {
    slice.columns[column].shown.forEach((node, index) => {
      placed.set(node.id, { node, x: columnX[column], y: TOP + index * ROW });
    });
  }
  const rows = Math.max(1, ...graphColumns.map((column) => slice.columns[column].shown.length));
  const height = TOP + rows * ROW + 4;
  const max = slice.edges.reduce((top, edge) => Math.max(top, edge.phraseIds.length), 1);
  const litEdges = new Set(
    hover === null
      ? []
      : slice.edges
          .filter((edge) => edge.source === hover || edge.target === hover)
          .map((edge) => edge.id),
  );
  const focusNode = focus?.kind === "node" ? graph.nodes.get(focus.id) : undefined;
  const focusEdge = focus?.kind === "edge" ? graph.edges.find((e) => e.id === focus.id) : undefined;
  const focusName =
    focusNode !== undefined
      ? focusNode.label
      : focusEdge !== undefined
        ? `${graph.nodes.get(focusEdge.source)?.label ?? ""} → ${graph.nodes.get(focusEdge.target)?.label ?? ""}`
        : null;
  const evidence = slice.phraseIds.flatMap((id) => {
    const row = byId.get(id);
    return row === undefined ? [] : [row];
  });
  const folded = query.trim().toLowerCase();
  const matches =
    folded.length < 2
      ? []
      : [...graph.nodes.values()]
          .filter((node) => node.label.toLowerCase().includes(folded))
          .sort((a, b) => b.phrases - a.phrases)
          .slice(0, 8);
  const toggle = "flex items-center gap-2 text-sm text-stone-700";
  const field =
    "rounded-sm border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 focus-visible:outline-2 focus-visible:outline-teal-700";

  return (
    <section aria-labelledby="lineage-graph" className="space-y-4">
      <div className="space-y-1">
        <h3 id="lineage-graph" className="font-serif text-xl text-stone-900">
          Experimental associations: organisation → tabler → provision
        </h3>
        <p className="max-w-3xl text-sm leading-6 text-stone-600">
          Line thickness is the number of phrases. Click a node or a line to follow it and read its
          evidence.
        </p>
        <KindLegend />
      </div>
      <div className="flex flex-wrap items-end gap-4 rounded-sm border border-stone-200 bg-white p-3">
        <label className="relative flex min-w-56 flex-col gap-1 text-xs text-stone-600">
          Find a node
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="organisation, Member, group or Art. 10"
            className={field}
          />
          {matches.length > 0 && (
            <ul className="absolute top-full z-30 mt-1 w-full rounded-sm border border-stone-300 bg-white shadow">
              {matches.map((node) => (
                <li key={node.id}>
                  <button
                    type="button"
                    className="w-full px-3 py-1.5 text-left text-sm text-stone-800 hover:bg-stone-100"
                    onClick={() => {
                      choose({ kind: "node", id: node.id });
                      setQuery("");
                    }}
                  >
                    {node.label}{" "}
                    <span className="text-xs text-stone-500">
                      · {columnTitle[node.column].toLowerCase()} · {node.phrases}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </label>
        <fieldset className="flex items-center gap-3">
          <legend className="sr-only">Tablers</legend>
          <label className={toggle}>
            <input
              type="radio"
              name="graph-tablers"
              checked={tablers === "group"}
              onChange={() => {
                setTablers("group");
                choose(null);
              }}
            />
            Political groups
          </label>
          <label className={toggle}>
            <input
              type="radio"
              name="graph-tablers"
              checked={tablers === "member"}
              onChange={() => {
                setTablers("member");
                choose(null);
              }}
            />
            Members
          </label>
        </fieldset>

        <label className={toggle}>
          <input
            type="checkbox"
            checked={lexical}
            onChange={(event) => setLexical(event.target.checked)}
          />
          Lexical lines
        </label>
        <label className={toggle}>
          <input
            type="checkbox"
            checked={semantic}
            onChange={(event) => setSemantic(event.target.checked)}
          />
          Semantic lines
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm" role="status">
        {focusName === null ? (
          <span className="text-stone-600">
            Overview: {count.format(graph.nodes.size)} nodes and {count.format(graph.edges.length)}{" "}
            lines in all.
          </span>
        ) : (
          <>
            <span className="text-stone-900">
              Following <strong>{focusName}</strong>: {count.format(slice.phraseIds.length)}{" "}
              phrases.
            </span>
            <button type="button" onClick={() => choose(null)} className={retryStyle}>
              Back to the overview
            </button>
          </>
        )}
      </div>
      <div className="overflow-x-auto rounded-sm border border-stone-200 bg-stone-50">
        {graph.edges.length === 0 ? (
          <p className="p-4 text-sm text-stone-600">
            No eligible organisation association is recorded with these settings.
          </p>
        ) : (
          <svg
            viewBox={`-10 0 ${VIEW_WIDTH + 20} ${height}`}
            className="min-w-[900px]"
            aria-label="Lineage graph"
          >
            {graphColumns.map((column) => (
              <text
                key={column}
                x={columnX[column]}
                y={16}
                fontSize={11}
                fontWeight={600}
                letterSpacing="0.12em"
                fill="#57534e"
              >
                {columnTitle[column].toUpperCase()}
              </text>
            ))}
            {slice.edges.map((edge) => {
              const from = placed.get(edge.source);
              const to = placed.get(edge.target);
              if (from === undefined || to === undefined) {
                return null;
              }
              return (
                <EdgePath
                  key={edge.id}
                  edge={edge}
                  from={from}
                  to={to}
                  max={max}
                  lit={litEdges.has(edge.id)}
                  dim={hover !== null && !litEdges.has(edge.id)}
                  selected={focus?.kind === "edge" && focus.id === edge.id}
                  onSelect={() => choose({ kind: "edge", id: edge.id })}
                />
              );
            })}
            {[...placed.values()].map((item) => (
              <NodeBox
                key={item.node.id}
                placed={item}
                selected={focus?.kind === "node" && focus.id === item.node.id}
                onSelect={() =>
                  choose(
                    focus?.kind === "node" && focus.id === item.node.id
                      ? null
                      : { kind: "node", id: item.node.id },
                  )
                }
                onHover={setHover}
              />
            ))}
          </svg>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-stone-500">
        {graphColumns.map((column) => (
          <span key={column}>
            {columnTitle[column]}: {count.format(slice.columns[column].shown.length)} shown
            {slice.columns[column].hidden > 0
              ? `, ${count.format(slice.columns[column].hidden)} more`
              : ""}
          </span>
        ))}
        {graphColumns.some((column) => slice.columns[column].hidden > 0) && (
          <button
            type="button"
            onClick={() => setLimit((value) => value + GRAPH_NODES_PER_COLUMN)}
            className={retryStyle}
          >
            Show {GRAPH_NODES_PER_COLUMN} more per column
          </button>
        )}
        {limit > GRAPH_NODES_PER_COLUMN && (
          <button
            type="button"
            onClick={() => setLimit(GRAPH_NODES_PER_COLUMN)}
            className={retryStyle}
          >
            Fewer
          </button>
        )}
      </div>
      {focusName !== null && (
        <div className="space-y-3">
          <h4 className="text-[11px] font-semibold uppercase tracking-[0.13em] text-stone-600">
            Evidence behind {focusName}
          </h4>
          <ol className="space-y-3">
            {evidence.slice(0, shownPhrases).map((row) => renderPhrase(row))}
          </ol>
          {evidence.length > shownPhrases && (
            <button
              type="button"
              onClick={() => setShownPhrases((value) => value + PHRASES_SHOWN)}
              className={retryStyle}
            >
              Show more ({count.format(evidence.length - shownPhrases)} left)
            </button>
          )}
        </div>
      )}
    </section>
  );
}
