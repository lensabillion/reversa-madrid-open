// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { act } from "react";
import { afterEach, expect, test, vi } from "vitest";
import HomePage from "../app/page";
import type {
  AmendmentDetail,
  AmendmentPage,
  AmendmentSummary,
  DatasetOverview,
  ScoreResult,
  SourceMatch,
} from "../lib/api";

const first: AmendmentSummary = {
  id: "a1",
  committee: "itre",
  number: 12,
  authors: ["Ada Example"],
  relations: ["a6p4"],
  verified_links: 1,
  candidate_links: 2,
};
const second: AmendmentSummary = {
  ...first,
  id: "a2",
  committee: "libe",
  number: 13,
  authors: ["Ben Example"],
  verified_links: 0,
  candidate_links: 0,
};
const overview: DatasetOverview = {
  amendments: 2,
  proposals: 2,
  documents: 2,
  organizations: 2,
  candidate_links: 2,
  duplicate_candidate_rows: 0,
  verified_links: 1,
  source_url: "https://github.com/lobbyplag/lobbyplag-data",
  coverage_note: "Historical links are incomplete.",
};
const score: ScoreResult = {
  score: 1,
  score_type: "lexical_similarity",
  method: "lexical-delta-v1",
  amendment_changes: [],
  submission_changes: [],
  evidence: [
    {
      operation: "insert",
      amendment: { start: 0, end: 5, text: "shall" },
      submission: { start: 0, end: 5, text: "shall" },
    },
    {
      operation: "delete",
      amendment: { start: 0, end: 3, text: "may" },
      submission: { start: 0, end: 3, text: "may" },
    },
  ],
  negation_conflict: false,
  limitations: ["Lexical overlap only."],
};
const sources: SourceMatch[] = [
  {
    candidate_id: "c1",
    proposal_id: "p1",
    organization_id: "o1",
    organization: "Civic Group",
    document_id: "d1",
    document: "civic.pdf",
    page: "3",
    text: { language: "en", old: "may notify", new: "shall notify" },
    historically_verified: true,
    score,
    score_unavailable_reason: null,
  },
  {
    candidate_id: "c2",
    proposal_id: "p2",
    organization_id: "o2",
    organization: "Trade Group",
    document_id: "d2",
    document: "trade.pdf",
    page: "8",
    text: { language: "fr", old: "peut notifier", new: "doit notifier" },
    historically_verified: false,
    score: null,
    score_unavailable_reason: "Only English text can be scored.",
  },
];
const firstDetail: AmendmentDetail = {
  amendment: first,
  text: { language: "en", old: "may notify", new: "shall notify" },
  sources,
  total_sources: 2,
  coverage_note: overview.coverage_note,
};
const secondDetail: AmendmentDetail = {
  amendment: second,
  text: { language: "en", old: "may record", new: "shall record" },
  sources: [],
  total_sources: 0,
  coverage_note: overview.coverage_note,
};

function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetch(
  listResponse: (url: URL) => Response,
): ReturnType<typeof vi.fn<(input: RequestInfo | URL) => Promise<Response>>> {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/api/v1/demo") {
      return reply(overview);
    }
    if (url.pathname === "/api/v1/amendments") {
      return listResponse(url);
    }
    if (url.pathname === "/api/v1/amendments/a1") {
      return reply(firstDetail);
    }
    if (url.pathname === "/api/v1/amendments/a2") {
      return reply(secondDetail);
    }
    throw new Error(`Unexpected request: ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("loads evidence, then changes source and amendment without any graph request", async () => {
  const fetchMock = installFetch(() =>
    reply({ items: [first, second], total: 2, offset: 0, limit: 12 } satisfies AmendmentPage),
  );
  render(<HomePage />);

  expect(screen.getByRole("heading", { name: "GDPR amendments" })).toBeDefined();
  expect(screen.getByRole("link", { name: "Influence Atlas" }).getAttribute("href")).toBe("/atlas");
  expect(screen.getByText("Loading amendments…")).toBeDefined();
  expect(await screen.findByRole("heading", { name: "ITRE 12" })).toBeDefined();
  expect(screen.getByText("1.00")).toBeDefined();
  const evidence = screen.getByRole("region", { name: "Source evidence" });
  const original = within(evidence).getByRole("region", { name: "Before the amendment" });
  const proposed = within(evidence).getByRole("region", { name: "Lawmaker's proposal" });
  const lobby = within(evidence).getByRole("region", { name: "Lobby's proposal" });
  expect(within(lobby).getByText("The wording requested by Civic Group.")).toBeDefined();
  expect(within(lobby).getByText("civic.pdf · p. 3")).toBeDefined();
  expect(original.querySelector("mark")?.textContent).toBe("may");
  expect(proposed.querySelector("mark")?.textContent).toBe("shall");
  expect(lobby.querySelector("mark")?.textContent).toBe("shall");
  expect(screen.queryByRole("button", { name: "Original text" })).toBeNull();

  fireEvent.change(screen.getByRole("combobox", { name: "Source · 2 candidates" }), {
    target: { value: "c2" },
  });
  expect(
    within(screen.getByRole("region", { name: "Lobby's proposal" })).getByText("trade.pdf · p. 8"),
  ).toBeDefined();
  expect(screen.getByText("Only English text can be scored.")).toBeDefined();
  expect(
    within(screen.getByRole("region", { name: "Source evidence" })).getByText("—"),
  ).toBeDefined();
  expect(evidence.querySelectorAll("mark")).toHaveLength(0);

  expect(screen.queryByRole("button", { name: "Network" })).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: /libe 13/i }));
  expect(await screen.findByRole("heading", { name: "LIBE 13" })).toBeDefined();
  expect(screen.getByText("No source candidates recorded for this amendment.")).toBeDefined();
  expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/graph"))).toBe(false);
});

test("submitted search, filter and pagination request the selected slice", async () => {
  const fetchMock = installFetch((url) => {
    const q = url.searchParams.get("q");
    const offset = Number(url.searchParams.get("offset"));
    const items = q === "Ada" ? [first] : offset === 12 ? [second] : [first];
    return reply({ items, total: q === "Ada" ? 1 : 13, offset, limit: 12 } satisfies AmendmentPage);
  });
  render(<HomePage />);
  expect(await screen.findByRole("heading", { name: "ITRE 12" })).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: "Next →" }));
  expect(await screen.findByRole("heading", { name: "LIBE 13" })).toBeDefined();

  fireEvent.change(screen.getByRole("textbox", { name: "Amendments" }), {
    target: { value: "Ada" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search amendments" }));
  expect(await screen.findByRole("heading", { name: "ITRE 12" })).toBeDefined();
  expect(
    fetchMock.mock.calls.some(([input]) =>
      String(input).includes("q=Ada&offset=0&limit=12&verified_only=true"),
    ),
  ).toBe(true);

  fireEvent.click(screen.getByRole("checkbox", { name: "Verified links only" }));
  expect(
    fetchMock.mock.calls.some(([input]) => String(input).includes("verified_only=false")),
  ).toBe(true);
});

test("dataset failure shows an error and retry restores the browser", async () => {
  let attempts = 0;
  installFetch((url) => {
    if (url.pathname === "/api/v1/amendments" && attempts++ === 0) {
      return reply({ detail: "unavailable" }, 503);
    }
    return reply({ items: [first], total: 1, offset: 0, limit: 12 } satisfies AmendmentPage);
  });
  render(<HomePage />);

  expect((await screen.findByRole("alert")).textContent).toContain(
    "The local dataset is unavailable.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Retry amendments" }));
  expect(await screen.findByRole("heading", { name: "ITRE 12" })).toBeDefined();
});

test("a late response cannot replace the newly selected amendment", async () => {
  let resolveFirst: ((response: Response) => void) | undefined;
  const pendingFirst = new Promise<Response>((resolve) => {
    resolveFirst = resolve;
  });
  let firstRequested = false;
  vi.stubGlobal("fetch", (input: RequestInfo | URL): Promise<Response> => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path === "/api/v1/demo") {
      return Promise.resolve(reply(overview));
    }
    if (path === "/api/v1/amendments") {
      return Promise.resolve(
        reply({ items: [first, second], total: 2, offset: 0, limit: 12 } satisfies AmendmentPage),
      );
    }
    if (path === "/api/v1/amendments/a1") {
      firstRequested = true;
      return pendingFirst;
    }
    if (path === "/api/v1/amendments/a2") {
      return Promise.resolve(reply(secondDetail));
    }
    throw new Error(`Unexpected request: ${path}`);
  });
  render(<HomePage />);
  await waitFor(() => expect(firstRequested).toBe(true));

  fireEvent.click(screen.getByRole("button", { name: /libe 13/i }));
  expect(await screen.findByRole("heading", { name: "LIBE 13" })).toBeDefined();
  const completion = act(async () => {
    resolveFirst?.(reply(firstDetail));
    await pendingFirst;
  });
  await Promise.resolve(completion);
  expect(screen.getByRole("heading", { name: "LIBE 13" })).toBeDefined();
  expect(screen.queryByRole("heading", { name: "ITRE 12" })).toBeNull();
});
