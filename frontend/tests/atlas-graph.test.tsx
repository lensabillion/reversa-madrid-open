// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import {
  AtlasGraph,
  type AtlasGraphSnapshot,
  graphLayout,
  overlaps,
} from "../components/atlas-graph";

const snapshot: AtlasGraphSnapshot = {
  snapshot_id: "snapshot:test",
  nodes: [
    { node_id: "actor:group", kind: "actor", label: "Example group", record_id: "actor:group" },
    { node_id: "ask:logs", kind: "ask", label: "Keep logs", record_id: "ask:logs" },
    {
      node_id: "am:procedure:101",
      kind: "amendment",
      label: "am:procedure:101",
      record_id: "am:procedure:101",
    },
    { node_id: "art:6", kind: "article", label: "Article 6", record_id: "art:6" },
  ],
  edges: [
    {
      edge_id: "edge:request",
      relation: "REQUESTED",
      source: "actor:group",
      target: "ask:logs",
      spans: [],
      link_id: null,
      outcome_id: null,
      dated_on: null,
    },
    {
      edge_id: "edge:echo",
      relation: "ECHOED_BY",
      source: "ask:logs",
      target: "am:procedure:101",
      spans: [{ record_id: "doc:request", field: "text", start: 0, end: 9, text: "Keep logs" }],
      link_id: "link:logs",
      outcome_id: null,
      dated_on: "2024-01-02",
    },
    {
      edge_id: "edge:final",
      relation: "REALIZED_IN",
      source: "ask:logs",
      target: "art:6",
      spans: [{ record_id: "art:6", field: "text", start: 0, end: 9, text: "Keep logs" }],
      link_id: null,
      outcome_id: "outcome:final",
      dated_on: "2024-02-03",
    },
  ],
};
afterEach(cleanup);

test("draws only supplied edges, retaining request-to-final direction and readable amendment labels", () => {
  const { container } = render(<AtlasGraph snapshot={snapshot} />);
  expect(container.querySelectorAll("path[data-edge-id]").length).toBe(3);
  expect(
    screen.getByRole("button", { name: "Keep logs reflected in final text Article 6" }),
  ).toBeDefined();
  expect(screen.queryByRole("button", { name: /Amendment 101 reflected in/ })).toBeNull();
  expect(screen.getByRole("button", { name: "Amendment Amendment 101" })).toBeDefined();
  expect(screen.queryByRole("button", { name: "am:procedure:101" })).toBeNull();
  expect(screen.getByRole("region", { name: "Graph canvas" }).className).toContain(
    "overflow-x-auto",
  );
});

test("connection selection exposes quoted evidence before opening its exact linked comparison", () => {
  const onSelectLink = vi.fn();
  render(<AtlasGraph snapshot={snapshot} onSelectLink={onSelectLink} />);
  fireEvent.click(screen.getByRole("button", { name: "Keep logs echoed in Amendment 101" }));
  const details = screen.getByRole("region", { name: "Graph selection" });
  expect(within(details).getByRole("heading", { name: "echoed in" })).toBeDefined();
  expect(details.querySelector("blockquote")?.textContent).toBe("Keep logs");
  expect(within(details).getByText("Dated 2024-01-02")).toBeDefined();
  expect(onSelectLink).not.toHaveBeenCalled();
  fireEvent.click(within(details).getByRole("button", { name: /Read source texts side by side/ }));
  expect(onSelectLink).toHaveBeenCalledExactlyOnceWith("link:logs");
});

test("identical request and amendment quotes are labelled by their source, not listed twice blind", () => {
  const echo = snapshot.edges[1];
  if (echo === undefined) {
    throw new Error("Echo edge missing from fixture");
  }
  const amendmentSpan = {
    record_id: "am:procedure:101",
    field: "new_text",
    start: 4,
    end: 13,
    text: "Keep logs",
  };
  render(
    <AtlasGraph
      snapshot={{
        ...snapshot,
        edges: snapshot.edges.map((edge) =>
          edge === echo ? { ...edge, spans: [...edge.spans, amendmentSpan] } : edge,
        ),
      }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Keep logs echoed in Amendment 101" }));
  const details = screen.getByRole("region", { name: "Graph selection" });
  const request = within(details).getByRole("figure", { name: "Request excerpt" });
  const amendment = within(details).getByRole("figure", { name: "Amendment excerpt" });
  expect(request.querySelector("figcaption")?.textContent).toBe("Request");
  expect(request.querySelector("blockquote")?.textContent).toBe("Keep logs");
  expect(amendment.querySelector("figcaption")?.textContent).toBe("Amendment");
  expect(amendment.querySelector("blockquote")?.textContent).toBe("Keep logs");
  expect(within(details).getAllByRole("figure")).toHaveLength(2);

  fireEvent.click(
    screen.getByRole("button", { name: "Keep logs reflected in final text Article 6" }),
  );
  expect(within(details).getByRole("figure", { name: "Final text excerpt" })).toBeDefined();
  expect(within(details).queryByRole("figure", { name: "Request excerpt" })).toBeNull();
});

/** A law-sized snapshot where several connections share a column gap and a card. */
const dense: AtlasGraphSnapshot = {
  snapshot_id: "snapshot:dense",
  nodes: [
    ...snapshot.nodes,
    { node_id: "actor:other", kind: "actor", label: "Other group", record_id: "actor:other" },
    { node_id: "ask:labels", kind: "ask", label: "Label energy", record_id: "ask:labels" },
    { node_id: "art:7", kind: "article", label: "Article 7", record_id: "art:7" },
    { node_id: "actor:mep", kind: "actor", label: "Example MEP", record_id: "actor:mep" },
    { node_id: "proc:1", kind: "procedure", label: "Example law", record_id: "proc:1" },
  ],
  edges: [
    ...snapshot.edges,
    ...(
      [
        ["REQUESTED", "actor:other", "ask:logs"],
        ["REQUESTED", "actor:group", "ask:labels"],
        ["REQUESTED", "actor:other", "ask:labels"],
        ["ECHOED_BY", "ask:labels", "am:procedure:101"],
        ["REALIZED_IN", "ask:labels", "art:7"],
        ["TABLED_BY", "am:procedure:101", "actor:mep"],
        ["ABOUT", "am:procedure:101", "proc:1"],
      ] as const
    ).map(([relation, source, target]) => ({
      edge_id: `edge:${relation}:${source}:${target}`,
      relation,
      source,
      target,
      spans: [],
      link_id: null,
      outcome_id: null,
      dated_on: null,
    })),
  ],
};

test("edge labels clear every card and every other label, and stay keyboard reachable", () => {
  const layout = graphLayout(dense);
  if (layout === null) {
    throw new Error("Dense fixture should lay out");
  }
  const cards = layout.nodes.map(({ x, y }) => ({ left: x, top: y, width: 184, height: 94 }));
  layout.paths.forEach((path, index) => {
    for (const card of cards) {
      expect(overlaps(path.label, card), `${path.edge.edge_id} overlaps a card`).toBe(false);
    }
    for (const other of layout.paths.slice(index + 1)) {
      expect(
        overlaps(path.label, other.label),
        `${path.edge.edge_id} overlaps ${other.edge.edge_id}`,
      ).toBe(false);
    }
    expect(path.label.left).toBeGreaterThanOrEqual(0);
    expect(path.label.left + path.label.width).toBeLessThanOrEqual(layout.canvasWidth);
    expect(path.label.top).toBeGreaterThanOrEqual(0);
    expect(path.label.top + path.label.height).toBeLessThanOrEqual(layout.canvasHeight);
  });
  // The overlap check itself must be able to fail.
  const box = { left: 0, top: 0, width: 10, height: 10 };
  expect(overlaps(box, { ...box, left: 12 })).toBe(true);
  expect(overlaps(box, { ...box, left: 15 })).toBe(false);

  const { container } = render(<AtlasGraph snapshot={dense} />);
  const labels = container.querySelectorAll<HTMLButtonElement>("button[data-edge-label]");
  expect(labels.length).toBe(dense.edges.length);
  for (const label of labels) {
    label.focus();
    expect(document.activeElement).toBe(label);
    expect(label.className).toContain("whitespace-nowrap");
    expect(label.className).toContain("bg-white");
  }
  const about = screen.getByRole("button", { name: "Amendment 101 concerns Example law" });
  expect(about.textContent).toBe("concerns");
  fireEvent.click(about);
  expect(about.getAttribute("aria-pressed")).toBe("true");
});

test("request selection shows actual connections and missing final evidence without inventing failure", () => {
  render(<AtlasGraph snapshot={{ ...snapshot, edges: snapshot.edges.slice(0, 2) }} />);
  fireEvent.click(screen.getByRole("button", { name: "Request Keep logs" }));
  const details = screen.getByRole("region", { name: "Graph selection" });
  expect(within(details).getAllByRole("button").length).toBe(2);
  expect(
    within(details).getByText("No final-text connection supplied for this request."),
  ).toBeDefined();
  expect(details.textContent).not.toContain("failed");
  fireEvent.click(
    within(details).getByRole("button", { name: "Example group requested Keep logs" }),
  );
  expect(within(details).getByText("Connection date unavailable")).toBeDefined();
  expect(
    within(details).getByText(
      "This is a supplied contextual relationship; no quoted text is attached.",
    ),
  ).toBeDefined();
  expect(within(details).queryByRole("button", { name: /Read source texts/ })).toBeNull();
});

test("contextual members are labelled and missing snapshots or dangling connections stay explicit", () => {
  const { rerender } = render(
    <AtlasGraph
      snapshot={{
        ...snapshot,
        nodes: [
          ...snapshot.nodes,
          { node_id: "actor:mep", kind: "actor", label: "Example MEP", record_id: "actor:mep" },
        ],
        edges: [
          ...snapshot.edges,
          {
            edge_id: "edge:tabled",
            source: "am:procedure:101",
            target: "actor:mep",
            relation: "TABLED_BY",
            spans: [],
            link_id: null,
            outcome_id: null,
            dated_on: null,
          },
        ],
      }}
    />,
  );
  expect(screen.getByRole("button", { name: "Parliament member Example MEP" })).toBeDefined();
  rerender(<AtlasGraph snapshot={{ snapshot_id: "empty", nodes: [], edges: [] }} />);
  expect(screen.getByText("No published graph is available in this snapshot.")).toBeDefined();
  rerender(<AtlasGraph snapshot={{ ...snapshot, nodes: snapshot.nodes.slice(0, 2) }} />);
  expect(screen.getByRole("alert").textContent).toContain("references a missing node");
});
