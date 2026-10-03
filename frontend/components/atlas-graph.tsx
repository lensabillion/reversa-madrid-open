"use client";

import { useId, useState } from "react";

interface AtlasGraphNode {
  node_id: string;
  kind: string;
  label: string;
  record_id: string;
}
interface AtlasGraphEdge {
  edge_id: string;
  relation: string;
  source: string;
  target: string;
  spans: readonly { record_id: string; field: string; start: number; end: number; text: string }[];
  link_id: string | null;
  outcome_id: string | null;
  dated_on: string | null;
}
/** Display projection of the shared snapshot; relationships remain pipeline supplied. */
export interface AtlasGraphSnapshot {
  snapshot_id: string;
  nodes: readonly AtlasGraphNode[];
  edges: readonly AtlasGraphEdge[];
}
const relations: Record<string, string> = {
  REQUESTED: "requested",
  ECHOED_BY: "echoed in",
  REALIZED_IN: "reflected in final text",
  TABLED_BY: "tabled by",
  EDITS: "edits",
  ALIGNED_TO: "aligned with",
  ABOUT: "concerns",
  MET_WITH: "met with",
  MEMBER_OF: "member of",
};
const kinds: Record<string, string> = {
  actor: "Actor",
  ask: "Request",
  amendment: "Amendment",
  article: "Legal provision",
  procedure: "Law",
  topic: "Topic",
};
const width = 184;
const step = 240;
const height = 94;

function caption(node: AtlasGraphNode): string {
  return node.kind === "amendment" && node.label === node.record_id
    ? `Amendment ${node.record_id.split(":").at(-1) ?? ""}`
    : node.label;
}

/** O(V log V + E) column layout for a law snapshot; positions never imply new edges. */
function positions(snapshot: AtlasGraphSnapshot) {
  const members = new Set(
    snapshot.edges.filter((edge) => edge.relation === "TABLED_BY").map((edge) => edge.target),
  );
  const asks = snapshot.nodes
    .filter((node) => node.kind === "ask")
    .sort((a, b) => a.node_id.localeCompare(b.node_id));
  const anchors = new Map(asks.map((node, index) => [node.node_id, index]));
  for (const edge of snapshot.edges) {
    if (edge.relation === "REQUESTED") {
      anchors.set(
        edge.source,
        Math.min(anchors.get(edge.source) ?? 1000000, anchors.get(edge.target) ?? 1000000),
      );
    } else if (edge.relation === "ECHOED_BY" || edge.relation === "REALIZED_IN") {
      anchors.set(
        edge.target,
        Math.min(anchors.get(edge.target) ?? 1000000, anchors.get(edge.source) ?? 1000000),
      );
    }
  }
  const column = (node: AtlasGraphNode) => {
    if (node.kind === "actor") {
      return members.has(node.node_id) ? 2 : 0;
    }
    if (node.kind === "ask") {
      return 1;
    }
    return node.kind === "amendment" ? 2 : 3;
  };
  const extra = (node: AtlasGraphNode) =>
    members.has(node.node_id) || node.kind === "procedure" || node.kind === "topic";
  const ordered = [...snapshot.nodes].sort(
    (a, b) =>
      Number(extra(a)) - Number(extra(b)) ||
      (anchors.get(a.node_id) ?? 1000000) - (anchors.get(b.node_id) ?? 1000000) ||
      a.node_id.localeCompare(b.node_id),
  );
  const rows = [0, 0, 0, 0];
  const nodes = ordered.map((node) => {
    const col = column(node);
    const row = rows[col] ?? 0;
    rows[col] = row + 1;
    return { node, x: 24 + col * step, y: 94 + row * 140, member: members.has(node.node_id) };
  });
  return { nodes, canvasHeight: 128 + Math.max(1, ...rows) * 140 };
}

/** Select supplied graph records and open their source excerpts, without inference. */
export function AtlasGraph({
  snapshot,
  onSelectLink,
}: {
  snapshot: AtlasGraphSnapshot;
  onSelectLink?: (linkId: string) => void;
}) {
  const markerId = useId();
  const [selection, select] = useState<{ kind: "node" | "edge"; id: string } | null>(null);
  const { nodes, canvasHeight } = positions(snapshot);
  const byId = new Map(nodes.map((item) => [item.node.node_id, item]));
  const selectedNode = selection?.kind === "node" ? byId.get(selection.id)?.node : undefined;
  const selectedEdge =
    selection?.kind === "edge"
      ? snapshot.edges.find((edge) => edge.edge_id === selection.id)
      : undefined;
  const connections = selectedNode
    ? snapshot.edges.filter(
        (edge) => edge.source === selectedNode.node_id || edge.target === selectedNode.node_id,
      )
    : [];
  const paths = snapshot.edges.map((edge) => {
    const from = byId.get(edge.source);
    const to = byId.get(edge.target);
    if (!from || !to) {
      return null;
    }
    const startX = from.x + width;
    const startY = from.y + height / 2;
    const endY = to.y + height / 2;
    const sameColumn = from.x === to.x;
    const isFinal = edge.relation === "REALIZED_IN";
    const lane = Math.min(from.y, to.y) - 28;
    const d = isFinal
      ? `M ${startX} ${startY} H ${startX + 18} V ${lane} H ${to.x - 18} V ${endY} H ${to.x}`
      : sameColumn
        ? `M ${startX} ${startY} C ${startX + 38} ${startY}, ${startX + 38} ${endY}, ${startX} ${endY}`
        : `M ${startX} ${startY} C ${startX + 28} ${startY}, ${to.x - 28} ${endY}, ${to.x} ${endY}`;
    return {
      edge,
      d,
      name: `${caption(from.node)} ${relations[edge.relation] ?? edge.relation} ${caption(to.node)}`,
      x: sameColumn ? startX - 15 : (startX + to.x) / 2 - 34,
      y: isFinal ? lane - 12 : (startY + endY) / 2 - 12,
    };
  });
  if (paths.some((path) => path === null)) {
    return (
      <p role="alert" className="rounded-sm border border-amber-300 bg-amber-50 p-5 text-amber-950">
        Graph unavailable: a supplied connection references a missing node.
      </p>
    );
  }
  return (
    <section aria-label="Influence graph" className="min-w-0 space-y-5">
      <div className="max-w-3xl">
        <h2 className="font-serif text-2xl text-stone-900">Follow a request into the law</h2>
        <p className="mt-2 text-sm leading-6 text-stone-600">
          An organization makes a request. A published link connects that request to an amendment. A
          separate branch shows whether the request is reflected in final text. Select a card or a
          connection to read its evidence.
        </p>
        <p className="mt-2 text-xs text-stone-500">
          Connections are supplied by the pipeline. Shared wording does not establish causal
          authorship. Scroll sideways on smaller screens.
        </p>
      </div>
      {snapshot.nodes.length === 0 ? (
        <p className="rounded-sm border border-stone-200 p-6 text-stone-600">
          No published graph is available in this snapshot.
        </p>
      ) : (
        <section
          className="overflow-x-auto rounded-sm border border-stone-200 bg-stone-50"
          aria-label="Graph canvas"
        >
          <div className="relative" style={{ width: 936, height: canvasHeight }}>
            {["Who asked", "What they requested", "Proposed amendment", "Final text / context"].map(
              (heading, index) => (
                <p
                  key={heading}
                  className="absolute top-5 text-xs font-semibold uppercase tracking-wider text-stone-500"
                  style={{ left: 24 + index * step }}
                >
                  {heading}
                </p>
              ),
            )}
            <svg
              aria-hidden="true"
              className="pointer-events-none absolute inset-0"
              width="936"
              height={canvasHeight}
            >
              <defs>
                <marker
                  id={markerId}
                  markerWidth="8"
                  markerHeight="8"
                  refX="7"
                  refY="4"
                  orient="auto"
                >
                  <path d="M0 0 L8 4 L0 8 Z" fill="#0f766e" />
                </marker>
              </defs>
              {paths.map(
                (path) =>
                  path && (
                    <path
                      key={path.edge.edge_id}
                      data-edge-id={path.edge.edge_id}
                      d={path.d}
                      fill="none"
                      stroke="#0f766e"
                      strokeWidth={selectedEdge?.edge_id === path.edge.edge_id ? 3 : 1.5}
                      opacity={
                        selectedEdge && selectedEdge.edge_id !== path.edge.edge_id ? 0.3 : 0.7
                      }
                      markerEnd={`url(#${markerId})`}
                    />
                  ),
              )}
            </svg>
            {nodes.map(({ node, x, y, member }) => (
              <button
                key={node.node_id}
                type="button"
                aria-label={`${member ? "Parliament member" : (kinds[node.kind] ?? node.kind)} ${caption(node)}`}
                aria-pressed={selectedNode?.node_id === node.node_id}
                onClick={() => select({ kind: "node", id: node.node_id })}
                className={`absolute overflow-hidden rounded-md border bg-white p-3 text-left shadow-sm transition hover:border-teal-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 ${selectedNode?.node_id === node.node_id ? "border-teal-700 ring-2 ring-teal-100" : "border-stone-300"}`}
                style={{ left: x, top: y, width, height }}
              >
                <span className="block text-[10px] font-semibold uppercase tracking-wide text-teal-700">
                  {member ? "Parliament member" : (kinds[node.kind] ?? node.kind)}
                </span>
                <span className="mt-2 block line-clamp-2 text-sm font-medium leading-5 text-stone-900">
                  {caption(node)}
                </span>
              </button>
            ))}
            {paths.map(
              (path) =>
                path && (
                  <button
                    key={path.edge.edge_id}
                    type="button"
                    aria-label={path.name}
                    aria-pressed={selectedEdge?.edge_id === path.edge.edge_id}
                    onClick={() => select({ kind: "edge", id: path.edge.edge_id })}
                    className="absolute max-w-40 rounded border border-teal-200 bg-teal-50 px-1.5 py-1 text-[10px] font-medium leading-3 text-teal-900 shadow-sm hover:bg-teal-100 focus-visible:outline-2 focus-visible:outline-teal-700"
                    style={{ left: path.x, top: path.y }}
                  >
                    {relations[path.edge.relation] ?? path.edge.relation}
                  </button>
                ),
            )}
          </div>
        </section>
      )}
      <section
        aria-label="Graph selection"
        aria-live="polite"
        className="rounded-sm border border-stone-200 bg-white p-5"
      >
        {!selectedNode && !selectedEdge && (
          <p className="text-sm text-stone-600">
            Select an actor, request, amendment or connection above. The evidence will appear here.
          </p>
        )}
        {selectedNode && (
          <div className="space-y-3">
            <h3 className="font-serif text-xl">{caption(selectedNode)}</h3>
            <p className="text-xs text-stone-500">
              {kinds[selectedNode.kind] ?? selectedNode.kind} · {connections.length} supplied
              connections
            </p>
            {connections.length === 0 ? (
              <p className="text-sm text-stone-500">No connections supplied for this node.</p>
            ) : (
              <ul className="space-y-2">
                {paths
                  .filter(
                    (path) =>
                      path &&
                      (path.edge.source === selectedNode.node_id ||
                        path.edge.target === selectedNode.node_id),
                  )
                  .map(
                    (path) =>
                      path && (
                        <li key={path.edge.edge_id}>
                          <button
                            type="button"
                            onClick={() => select({ kind: "edge", id: path.edge.edge_id })}
                            className="text-left text-sm text-teal-800 underline underline-offset-4"
                          >
                            {path.name}
                          </button>
                        </li>
                      ),
                  )}
              </ul>
            )}
            {selectedNode.kind === "ask" &&
              !connections.some(
                (edge) => edge.source === selectedNode.node_id && edge.relation === "REALIZED_IN",
              ) && (
                <p className="text-sm text-amber-900">
                  No final-text connection supplied for this request.
                </p>
              )}
          </div>
        )}
        {selectedEdge && (
          <div className="space-y-4">
            <h3 className="font-serif text-xl">
              {relations[selectedEdge.relation] ?? selectedEdge.relation}
            </h3>
            <p className="text-xs text-stone-500">
              {selectedEdge.dated_on === null
                ? "Connection date unavailable"
                : `Dated ${selectedEdge.dated_on}`}
            </p>
            {selectedEdge.spans.length === 0 ? (
              <p className="text-sm text-stone-600">
                This is a supplied contextual relationship; no quoted text is attached.
              </p>
            ) : (
              <div className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Supplied evidence excerpts
                </p>
                {selectedEdge.spans.map((span) => (
                  <blockquote
                    key={`${span.record_id}:${span.field}:${span.start}:${span.end}`}
                    className="border-l-2 border-teal-300 pl-4 font-serif text-base leading-7 text-stone-800"
                  >
                    {span.text}
                  </blockquote>
                ))}
              </div>
            )}
            {selectedEdge.link_id !== null && onSelectLink && (
              <button
                type="button"
                onClick={() => {
                  if (selectedEdge.link_id !== null) {
                    onSelectLink(selectedEdge.link_id);
                  }
                }}
                className="rounded-sm bg-teal-800 px-4 py-2 text-sm font-medium text-white hover:bg-teal-900"
              >
                Read source texts side by side →
              </button>
            )}
          </div>
        )}
      </section>
    </section>
  );
}
