"use client";

import { useState } from "react";
import type { GraphNode, InfluenceGraph } from "../lib/api";
import { useResource } from "../lib/use-resource";

/** A small deterministic graph keeps source links inspectable without a layout dependency. */
export function InfluenceNetwork({ amendmentId }: { amendmentId: string }) {
  const resource = useResource<InfluenceGraph>(
    `/api/v1/amendments/${encodeURIComponent(amendmentId)}/graph`,
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  if (resource.error) {
    return (
      <div role="alert" className="p-8 text-sm text-stone-600">
        {resource.error}{" "}
        <button
          type="button"
          onClick={resource.retry}
          className="ml-3 text-teal-800 underline underline-offset-4"
        >
          Retry
        </button>
      </div>
    );
  }
  if (!resource.data) {
    return (
      <p role="status" className="p-8 text-sm text-stone-500">
        Loading network…
      </p>
    );
  }
  const graph = resource.data;
  const organizations = graph.nodes.filter((node) => node.kind === "organization");
  const authors = graph.nodes.filter((node) => node.kind === "author");
  const height = Math.max(320, Math.max(organizations.length, authors.length) * 72 + 80);
  const positions = new Map<string, { x: number; y: number }>();
  for (const node of graph.nodes) {
    const column = node.kind === "organization" ? organizations : authors;
    const index = column.findIndex((item) => item.id === node.id);
    positions.set(
      node.id,
      node.kind === "amendment"
        ? { x: 380, y: height / 2 }
        : {
            x: node.kind === "organization" ? 120 : 640,
            y: ((index + 1) * height) / (column.length + 1),
          },
    );
  }
  const selected =
    graph.nodes.find((node) => node.id === selectedId) ??
    graph.nodes.find((node) => node.kind === "amendment");
  const labels: Record<GraphNode["kind"], string> = {
    amendment: "Amendment",
    organization: "Verified source",
    author: "Author",
  };
  return (
    <section aria-label="Influence network" className="py-6">
      <div className="mb-4 flex justify-between text-[11px] font-medium uppercase tracking-[0.14em] text-stone-500">
        <span>Verified sources</span>
        <span>Amendment</span>
        <span>Authors</span>
      </div>
      <fieldset
        aria-label="Network nodes"
        className="min-w-0 overflow-x-auto rounded-sm border border-stone-200 bg-white"
      >
        <svg
          viewBox={`0 0 760 ${height}`}
          className="w-full min-w-[560px]"
          aria-label="Historical links between organizations, amendment and authors"
        >
          <title>Verified source and author network</title>
          {graph.edges.map((edge) => {
            const from = positions.get(edge.source);
            const to = positions.get(edge.target);
            if (!from || !to) {
              return null;
            }
            return (
              <line
                key={`${edge.source}:${edge.target}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={edge.kind === "historically_verified" ? "#8bbdb2" : "#d6d3d1"}
                strokeWidth="1.5"
              />
            );
          })}
          {graph.nodes.map((node) => {
            const position = positions.get(node.id);
            if (!position) {
              return null;
            }
            return (
              <g key={node.id}>
                <circle
                  cx={position.x}
                  cy={position.y}
                  r={node.kind === "amendment" ? 28 : 13}
                  fill={
                    node.kind === "amendment"
                      ? "#19483e"
                      : node.kind === "organization"
                        ? "#d2e9e1"
                        : "#eeeae3"
                  }
                  stroke={selected?.id === node.id ? "#19483e" : "#fff"}
                  strokeWidth="3"
                />
                <foreignObject
                  x={position.x - 110}
                  y={position.y - (node.kind === "amendment" ? 30 : 15)}
                  width="220"
                  height={node.kind === "amendment" ? 105 : 70}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedId(node.id)}
                    aria-pressed={selected?.id === node.id}
                    className="flex h-full w-full items-end justify-center rounded px-1 pb-1 text-center text-[12px] leading-4 text-stone-700 hover:text-teal-900 focus-visible:outline-2 focus-visible:outline-teal-700"
                  >
                    <span className="line-clamp-2">{node.label}</span>
                  </button>
                </foreignObject>
              </g>
            );
          })}
        </svg>
      </fieldset>
      {selected && (
        <p aria-live="polite" className="mt-4 text-sm text-stone-600">
          <span className="mr-3 text-[11px] uppercase tracking-wider text-stone-400">
            {labels[selected.kind]}
          </span>
          {selected.label}
        </p>
      )}
      {organizations.length === 0 && (
        <p className="mt-3 text-sm text-stone-500">
          No historically verified source links for this amendment.
        </p>
      )}
      <p className="mt-6 max-w-2xl text-xs leading-5 text-stone-500">
        Historical links are incomplete and do not establish causation or adoption.
      </p>
    </section>
  );
}
