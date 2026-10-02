// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { act } from "react";
import { afterEach, expect, test, vi } from "vitest";
import { CompareTexts } from "../components/compare-texts";
import type { ComparisonResult } from "../lib/api";

const score: ComparisonResult = {
  mode: "edits",
  score: 0.75,
  method: "lexical-delta-v1",
  evidence: [
    {
      operation: "insert",
      amendment: { start: 0, end: 5, text: "shall" },
      submission: { start: 0, end: 5, text: "shall" },
    },
  ],
  negation_conflict: false,
  limitations: ["Lexical overlap only."],
};

function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function enterPair(): void {
  fireEvent.change(screen.getByRole("textbox", { name: "Amendment" }), {
    target: { value: "shall notify" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Lobby submission or comment" }), {
    target: { value: "shall notify" },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("submits both old and new texts and displays the score with evidence", async () => {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => reply(score));
  vi.stubGlobal("fetch", fetchMock);
  render(<CompareTexts />);
  enterPair();
  fireEvent.change(screen.getByRole("textbox", { name: "Original amendment" }), {
    target: { value: "may notify" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Original submission" }), {
    target: { value: "may notify" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));

  const result = await screen.findByLabelText("Comparison result");
  expect(result.textContent).toContain("Edit overlap");
  expect(result.textContent).toContain("0.75");
  expect(result.querySelector("mark")?.textContent).toBe("shall");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, options] = fetchMock.mock.calls[0] ?? [];
  expect(url).toBe("/api/v1/compare");
  expect(options?.method).toBe("POST");
  expect(JSON.parse(String(options?.body))).toEqual({
    amendment: { old: "may notify", new: "shall notify" },
    submission: { old: "may notify", new: "shall notify" },
  });
});

test("compares proposed texts when only one original is supplied", async () => {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    reply({ ...score, mode: "passages", method: "lexical-passage-v1" }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<CompareTexts />);
  enterPair();
  fireEvent.change(screen.getByRole("textbox", { name: "Original amendment" }), {
    target: { value: "may notify" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));

  expect((await screen.findByLabelText("Comparison result")).textContent).toContain("Text overlap");
  const [, options] = fetchMock.mock.calls[0] ?? [];
  expect(JSON.parse(String(options?.body))).toEqual({
    amendment: { old: "may notify", new: "shall notify" },
    submission: { old: null, new: "shall notify" },
  });
});

test("submits pure deletions when both original texts are present", async () => {
  const deletion: ComparisonResult = {
    ...score,
    evidence: [
      {
        operation: "delete",
        amendment: { start: 0, end: 6, text: "remove" },
        submission: { start: 0, end: 6, text: "remove" },
      },
    ],
  };
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    reply(deletion),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<CompareTexts />);
  fireEvent.change(screen.getByRole("textbox", { name: "Original amendment" }), {
    target: { value: "remove clause" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Original submission" }), {
    target: { value: "remove clause" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
  const result = await screen.findByLabelText("Comparison result");
  expect(within(result).getByRole("region", { name: "Original law" })).toBeDefined();
  expect(within(result).getByRole("region", { name: "Proposed amendment" }).textContent).toContain(
    "No proposed wording (deletion)",
  );
  const lobby = within(result).getByRole("region", { name: "Lobby submission" });
  expect(lobby.querySelector("details")?.open).toBe(true);
  expect(lobby.querySelector("mark")?.textContent).toBe("remove");
  expect(screen.queryByRole("button", { name: "Original text" })).toBeNull();
  expect(result.querySelector("mark")?.textContent).toBe("remove");
  const [, options] = fetchMock.mock.calls[0] ?? [];
  expect(JSON.parse(String(options?.body))).toEqual({
    amendment: { old: "remove clause", new: "" },
    submission: { old: "remove clause", new: "" },
  });
});

test.each([413, 502])("shows a concise extraction error for non-JSON HTTP %s", async (status) => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response("<html>Upstream failure</html>", {
          status,
          headers: { "Content-Type": "text/html" },
        }),
    ),
  );
  render(<CompareTexts />);
  fireEvent.change(screen.getByLabelText("Amendment file"), {
    target: { files: [new File(["%PDF"], "sample.pdf", { type: "application/pdf" })] },
  });
  const error = await screen.findByRole("alert");
  expect(error.textContent).toContain(`Extraction failed (${status})`);
  expect(error.textContent).not.toMatch(/Unexpected token|JSON|html/i);
});

test("reviews an extracted page before using it and rejects unsupported or oversized files", async () => {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    reply({
      format: "text",
      pages: [
        { page: 1, text: "shall notify" },
        { page: 2, text: "shall record" },
      ],
      warnings: [],
      character_count: 25,
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<CompareTexts />);
  const input = screen.getByLabelText("Amendment file");
  fireEvent.change(input, {
    target: { files: [new File(["shall notify"], "amendment.md", { type: "text/markdown" })] },
  });
  expect(await screen.findByLabelText("Amendment file preview")).toBeDefined();
  expect((screen.getByRole("textbox", { name: "Amendment" }) as HTMLTextAreaElement).value).toBe(
    "",
  );
  const [url, options] = fetchMock.mock.calls[0] ?? [];
  expect(url).toBe("/api/v1/documents/extract");
  expect(options?.body).toBeInstanceOf(File);
  expect(options?.headers).toEqual({ "Content-Type": "text/markdown" });
  fireEvent.change(screen.getByRole("combobox", { name: "Amendment file page" }), {
    target: { value: "2" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Amendment file extracted text" }), {
    target: { value: "shall disclose" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Use page text" }));
  expect((screen.getByRole("textbox", { name: "Amendment" }) as HTMLTextAreaElement).value).toBe(
    "shall disclose",
  );
  expect(screen.getByText(/amendment\.md · p\. 2 · edited/)).toBeDefined();

  fireEvent.change(input, {
    target: { files: [new File(["DOC"], "paper.doc", { type: "application/msword" })] },
  });
  expect((await screen.findByRole("alert")).textContent).toMatch(/\.pdf|\.txt|\.md/i);

  fireEvent.change(input, {
    target: {
      files: [new File(["x".repeat(8 * 1024 * 1024 + 1)], "huge.txt", { type: "text/plain" })],
    },
  });
  expect((await screen.findByRole("alert")).textContent).toMatch(/8 MiB/i);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("a late extraction cannot replace the preview for a newer PDF", async () => {
  let resolveOld: ((response: Response) => void) | undefined;
  const oldResponse = new Promise<Response>((resolve) => {
    resolveOld = resolve;
  });
  const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
    fetchMock.mock.calls.length === 1
      ? oldResponse
      : Promise.resolve(
          reply({
            format: "pdf",
            pages: [{ page: 3, text: "new PDF text" }],
            warnings: [],
            character_count: 12,
          }),
        ),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<CompareTexts />);
  const input = screen.getByLabelText("Amendment file");
  fireEvent.change(input, {
    target: { files: [new File(["old"], "old.txt", { type: "text/plain" })] },
  });
  fireEvent.change(input, {
    target: { files: [new File(["%PDF"], "new.pdf", { type: "application/pdf" })] },
  });
  expect(await screen.findByLabelText("Amendment file preview")).toBeDefined();
  expect(screen.getByText(/new\.pdf · 1 page/)).toBeDefined();
  expect(fetchMock.mock.calls[1]?.[1]?.headers).toEqual({ "Content-Type": "application/pdf" });
  const completion = act(async () => {
    resolveOld?.(
      reply({
        format: "text",
        pages: [{ page: 1, text: "old text" }],
        warnings: [],
        character_count: 8,
      }),
    );
    await oldResponse;
  });
  await Promise.resolve(completion);
  expect(screen.getByText(/new\.pdf · 1 page/)).toBeDefined();
});

test("shows a safe validation error when the scorer rejects the pair", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => reply({ detail: [{ msg: "Value error, Text is too long" }] }, 422)),
  );
  render(<CompareTexts />);
  enterPair();
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));

  expect((await screen.findByRole("alert")).textContent).toContain("Text is too long");
  expect(screen.queryByLabelText("Comparison result")).toBeNull();
});

test("editing clears a score and an old reply cannot replace newer input", async () => {
  let resolveLate: ((response: Response) => void) | undefined;
  const pending = new Promise<Response>((resolve) => {
    resolveLate = resolve;
  });
  let requests = 0;
  vi.stubGlobal("fetch", () => (requests++ === 0 ? Promise.resolve(reply(score)) : pending));
  render(<CompareTexts />);
  enterPair();
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
  expect(await screen.findByLabelText("Comparison result")).toBeDefined();

  fireEvent.change(screen.getByRole("textbox", { name: "Amendment" }), {
    target: { value: "shall record" },
  });
  expect(screen.queryByLabelText("Comparison result")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
  await waitFor(() => expect(requests).toBe(2));
  fireEvent.change(screen.getByRole("textbox", { name: "Amendment" }), {
    target: { value: "shall erase" },
  });
  const completion = act(async () => {
    resolveLate?.(reply(score));
    await pending;
  });
  await Promise.resolve(completion);
  expect(screen.queryByLabelText("Comparison result")).toBeNull();
});

test("shows simultaneous columns and missing originals in passage comparisons", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => reply({ ...score, mode: "passages", method: "lexical-passage-v1" })),
  );
  render(<CompareTexts />);
  enterPair();
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
  const result = await screen.findByLabelText("Comparison result");
  for (const name of ["Original law", "Proposed amendment", "Lobby submission"]) {
    expect(within(result).getByRole("heading", { name })).toBeDefined();
  }
  expect(within(result).getByText("Original wording not supplied")).toBeDefined();
  expect(within(result).getByText("Shared wording")).toBeDefined();
  expect(within(result).queryByText("Shared added wording")).toBeNull();
});
