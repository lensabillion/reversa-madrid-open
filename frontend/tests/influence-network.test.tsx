// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { InfluenceNetwork } from "../components/influence-network";
import type { InfluenceGraph } from "../lib/api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("three author labels have separate click areas and each remains selectable", async () => {
  const authors = ["Ada Example", "Ben Example", "Cora Example"];
  const graph: InfluenceGraph = {
    amendment_id: "a1",
    nodes: [
      { id: "amendment:a1", kind: "amendment", label: "ITRE 12" },
      ...authors.map((name) => ({ id: `author:${name}`, kind: "author" as const, label: name })),
    ],
    edges: authors.map((name) => ({
      source: `author:${name}`,
      target: "amendment:a1",
      kind: "authored" as const,
    })),
    coverage_note: "Historical links are incomplete.",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(graph), { status: 200 })),
  );
  render(<InfluenceNetwork amendmentId="a1" />);
  const nodes = await screen.findByRole("group", { name: "Network nodes" });
  const boxes = authors.map((name) => {
    const box = within(nodes).getByRole("button", { name }).parentElement;
    if (!box) {
      throw new Error(`Missing click area for ${name}`);
    }
    expect(box.localName.toLowerCase()).toBe("foreignobject");
    return { top: Number(box.getAttribute("y")), height: Number(box.getAttribute("height")) };
  });
  for (let index = 1; index < boxes.length; index++) {
    const previous = boxes[index - 1];
    const current = boxes[index];
    if (!previous || !current) {
      throw new Error("Missing author click area");
    }
    expect(current.top).toBeGreaterThanOrEqual(previous.top + previous.height);
  }

  for (const name of authors) {
    const button = within(nodes).getByRole("button", { name });
    fireEvent.click(button);
    expect(button.getAttribute("aria-pressed")).toBe("true");
  }
});
