// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { EvidenceColumns } from "../components/evidence-columns";
import type { ScoreResult } from "../lib/api";

const amendment = { old: "😀 may act.", new: "😀 shall act.", language: "en" };
const submission = { old: "may act.", new: "shall act.", language: "en" };
const evidence: ScoreResult["evidence"] = [
  {
    operation: "delete",
    amendment: { start: 2, end: 5, text: "may" },
    submission: { start: 0, end: 3, text: "may" },
  },
  {
    operation: "insert",
    amendment: { start: 2, end: 7, text: "shall" },
    submission: { start: 0, end: 5, text: "shall" },
  },
];

afterEach(cleanup);

test("maps Unicode insertion and deletion evidence to its exact source column", () => {
  render(
    <EvidenceColumns
      amendment={amendment}
      submission={submission}
      evidence={evidence}
      mode="edits"
      sourceMetadata={null}
    />,
  );
  const original = screen.getByRole("region", { name: "Before the amendment" });
  const proposed = screen.getByRole("region", { name: "Lawmaker's proposal" });
  const lobby = screen.getByRole("region", { name: "Lobby's proposal" });
  expect(
    within(original).getByText("The draft wording the lawmaker wants to change."),
  ).toBeDefined();
  expect(within(proposed).getByText("The wording the lawmaker proposes instead.")).toBeDefined();
  expect(
    within(lobby).getByText("The wording supplied in the lobby submission or comment."),
  ).toBeDefined();
  expect(original.querySelector("mark")?.textContent).toBe("may");
  expect(original.querySelector("mark")?.className).toContain("line-through");
  expect(proposed.querySelector("mark")?.textContent).toBe("shall");
  expect(proposed.querySelector("mark")?.className).not.toContain("line-through");
  expect([...lobby.querySelectorAll("mark")].map((mark) => mark.textContent)).toEqual([
    "shall",
    "may",
  ]);
  expect(lobby.querySelector("details")?.open).toBe(false);
  expect(within(lobby).getByText("Original lobby wording")).toBeDefined();
  expect(screen.getByText("Shared added wording")).toBeDefined();
  expect(screen.getByText("Shared removed wording")).toBeDefined();
});

test("keeps a complete supplied excerpt and no-source column without manufacturing evidence", () => {
  const fullText = `${"Supplied paragraph.\n\n".repeat(50)}Final supplied sentence.`;
  render(
    <EvidenceColumns
      amendment={{ ...amendment, new: fullText }}
      submission={null}
      evidence={[]}
      mode="edits"
      sourceMetadata={null}
    />,
  );
  expect(screen.getByRole("region", { name: "Lawmaker's proposal" }).textContent).toContain(
    fullText,
  );
  expect(screen.getByText("No lobby submission available")).toBeDefined();
  expect(document.querySelectorAll("mark")).toHaveLength(0);
});

test.each([
  [null, "Original wording not supplied"],
  ["", "No original wording (insertion)"],
])("distinguishes unknown original %s from a known empty source", (old, message) => {
  render(
    <EvidenceColumns
      amendment={{ ...amendment, old }}
      submission={submission}
      evidence={[]}
      mode="edits"
      sourceMetadata={null}
    />,
  );
  expect(
    within(screen.getByRole("region", { name: "Before the amendment" })).getByText(message),
  ).toBeDefined();
});
