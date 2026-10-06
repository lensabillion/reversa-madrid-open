// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import LineagePage from "../app/lineage/page";
import { PHRASES_PER_PAGE } from "../components/lineage-law-browser";
import type { LineageLawList, LineageView } from "../lib/lineage-api";
import { fixtureView } from "./lineage-fixture";

// Next.js re-renders `useSearchParams` readers after `history.pushState`; outside its router,
// this stand-in reads jsdom's URL and is notified by the pushState spy installed below.
const urlListeners = vi.hoisted(() => new Set<() => void>());
vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  const subscribe = (listener: () => void) => {
    urlListeners.add(listener);
    return () => urlListeners.delete(listener);
  };
  return {
    useSearchParams: () =>
      new URLSearchParams(useSyncExternalStore(subscribe, () => window.location.search)),
  };
});

const view = fixtureView();
const slug = view.slug;
const laws: LineageLawList = {
  laws: [
    {
      slug,
      procedure_id: view.procedure_id,
      title: view.title,
      run_id: view.run_id,
      status: view.status,
      adopted_phrases: view.counts.adopted_phrases,
      amendments_adopting: view.counts.amendments_adopting,
      documents_with_origin: view.counts.documents_with_origin,
    },
  ],
};

function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetch(route: (path: string) => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) =>
    route(new URL(String(input), "http://localhost").pathname),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openTab(name: string) {
  fireEvent.click(await screen.findByRole("tab", { name }));
}

const unexpected = (path: string): never => {
  throw new Error(`Unexpected request: ${path}`);
};

function serve(lawView: LineageView) {
  return installFetch((path) => {
    if (path === "/api/v1/lineage") {
      return reply(laws);
    }
    return path === `/api/v1/lineage/${slug}` ? reply(lawView) : unexpected(path);
  });
}

beforeEach(() => {
  window.history.replaceState(null, "", "/lineage");
  const push = window.history.pushState.bind(window.history);
  vi.spyOn(window.history, "pushState").mockImplementation((data, unused, url) => {
    push(data, unused, url);
    for (const listener of urlListeners) {
      listener();
    }
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("lists laws, opens one into the URL and shows adopted wording beside its sources", async () => {
  const fetchMock = serve(view);
  render(<LineagePage />);

  const selector = await screen.findByRole("navigation", { name: "Collected laws" });
  const law = await within(selector).findByRole("button", { name: /Artificial Intelligence Act/ });
  expect(law.textContent).toContain("1 adopted phrase");
  expect(screen.getByText("Choose a law")).toBeDefined();
  fireEvent.click(law);

  expect(window.location.search).toBe(`?law=${slug}`);
  const questions = await screen.findByRole("heading", {
    name: "The five questions, for this law",
  });
  expect(questions.closest("section")?.textContent).toContain(
    "Acme Unknown Lobby leads, with 1 adopted phrase said first.",
  );
  expect(questions.closest("section")?.textContent).toContain("No forecast yet");
  const summary = screen.getByRole("region", { name: "From proposal to law" });
  expect(within(summary).getByText("18 of 103 words")).toBeDefined();
  expect(within(summary).getByText("1 of 3 amendments")).toBeDefined();
  expect(within(summary).getByRole("img", { name: "17%: 18 of 103 words" })).toBeDefined();
  expect(screen.queryByRole("article")).toBeNull();
  await openTab("Evidence");
  const card = await screen.findByRole("article", { name: /Phrase phrase:/ });
  expect(within(card).getByText("In the final act")).toBeDefined();
  expect(within(card).getByText("am:2021-0106-COD:ENVI:PE7-7")).toBeDefined();
  expect(within(card).getByText("Acme Unknown Lobby")).toBeDefined();
  expect(within(card).getByText("Said before the amendments")).toBeDefined();
  expect(within(card).getAllByRole("blockquote")).toHaveLength(2);
  await openTab("Who");
  expect(
    screen.getByRole("heading", { name: "Who gets their way: Members and political groups" }),
  ).toBeDefined();
  const organisations = screen.getByRole("heading", { name: "Who gets their way: organisations" });
  const orgSection = organisations.closest("section");
  if (orgSection === null) {
    throw new Error("Organisation section missing");
  }
  expect(within(orgSection).getByRole("row", { name: /Acme Unknown Lobby/ })).toBeDefined();
  expect(screen.getByText("Political groups · lexical")).toBeDefined();
  expect(within(card).getByText(/joint: credited to several holders/)).toBeDefined();
  expect(within(card).getByText(/18 of 18 words in the final act/)).toBeDefined();
  const auken = screen.getByRole("row", { name: /Margrete AUKEN/ });
  expect(within(auken).getByText("1 of 2")).toBeDefined();
  expect(within(auken).getByText("50%")).toBeDefined();
  expect(within(auken).getByText("1 (1)")).toBeDefined();
  expect(screen.getByText(/Verbatim wording only/)).toBeDefined();
  expect(screen.getByText(/Meetings: not collected in this run/)).toBeDefined();
  expect(fetchMock.mock.calls.map(([input]) => String(input)).sort()).toEqual([
    "/api/v1/lineage",
    `/api/v1/lineage/${slug}`,
  ]);
});

test("the tabled tab, the evidence filter and the search change which phrases are shown", async () => {
  window.history.replaceState(null, "", `/lineage?law=${slug}`);
  serve(view);
  render(<LineagePage />);

  await openTab("Evidence");
  await screen.findByRole("article", { name: /Phrase phrase:/ });
  fireEvent.click(screen.getByRole("button", { name: "Tabled, not adopted (0)" }));
  expect(screen.getByText("No phrase matches this selection.")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Adopted (1)" }));
  expect(screen.getByRole("article", { name: /Phrase phrase:/ })).toBeDefined();
  const evidence = screen.getByRole("combobox", { name: "Evidence" });
  fireEvent.change(evidence, { target: { value: "first" } });
  expect(screen.getByRole("article", { name: /Phrase phrase:/ })).toBeDefined();
  fireEvent.change(evidence, { target: { value: "reworded" } });
  expect(screen.getByText("No phrase matches this selection.")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  const search = screen.getByRole("searchbox", {
    name: "Search words, organisations, Members or amendments",
  });
  fireEvent.change(search, { target: { value: "ACME logs" } });
  expect(screen.getByRole("article", { name: /Phrase phrase:/ })).toBeDefined();
  expect(screen.getByText("1 of 1 phrases shown, strongest evidence first")).toBeDefined();
  fireEvent.change(search, { target: { value: "acme biometric" } });
  expect(screen.getByText("No phrase matches this selection.")).toBeDefined();
  fireEvent.change(search, { target: { value: "" } });
  fireEvent.change(screen.getByRole("combobox", { name: "Political group" }), {
    target: { value: "S&D" },
  });
  expect(screen.getByRole("article", { name: /Phrase phrase:/ })).toBeDefined();
});

test("drawing three links shows the drawn link with its seed", async () => {
  window.history.replaceState(null, "", `/lineage?law=${slug}`);
  serve(view);
  vi.spyOn(crypto, "getRandomValues").mockImplementation((array) => {
    if (array instanceof Uint32Array) {
      array[0] = 42;
    }
    return array;
  });
  render(<LineagePage />);

  await openTab("Check 3 links");
  const heading = await screen.findByRole("heading", { name: "Check three links at random" });
  const section = heading.closest("section");
  if (section === null) {
    throw new Error("Link check section missing");
  }
  expect(within(section).queryByRole("article")).toBeNull();
  fireEvent.click(within(section).getByRole("button", { name: "Draw 3 links" }));
  expect(within(section).getByText(/Seed 42/)).toBeDefined();
  const drawn = within(section).getAllByRole("article");
  expect(drawn).toHaveLength(1);
  expect(within(drawn[0] as HTMLElement).getByText("Acme Unknown Lobby")).toBeDefined();
  expect(within(section).getByRole("button", { name: "Draw again" })).toBeDefined();
});

test("a long list is paged, and an undated or citing submission is labelled as such", async () => {
  window.history.replaceState(null, "", `/lineage?law=${slug}`);
  const [origin] = view.origins;
  if (origin === undefined) {
    throw new Error("Fixture origin missing");
  }
  const total = PHRASES_PER_PAGE + 3;
  const ids = Array.from(
    { length: total },
    (_, index) => `phrase:${String(index).padStart(16, "0")}`,
  );
  serve({
    ...view,
    adopted_phrases: [],
    adoptions: [],
    credits: [],
    tabled_phrases: ids.map((id) => ({
      phrase_id: id,
      text: `tabled wording ${id}`,
      words: 3,
      amendment_ids: ["am:1"],
    })),
    origins: [
      {
        ...origin,
        phrase_id: ids[0] ?? "",
        amendment_ids: ["am:1"],
        precedes: null,
        eligibility: "unknown_date",
      },
      { ...origin, phrase_id: ids[1] ?? "", amendment_ids: ["am:1"], is_citation: true },
      {
        ...origin,
        phrase_id: ids[2] ?? "",
        amendment_ids: ["am:1"],
        precedes: false,
        eligibility: "amendment_first",
      },
    ],
  });
  render(<LineagePage />);

  await openTab("Who");
  await screen.findByText("No adopted wording, so no credit.");
  await openTab("Evidence");
  fireEvent.click(screen.getByRole("button", { name: `Tabled, not adopted (${total})` }));
  expect(screen.getAllByRole("article")).toHaveLength(PHRASES_PER_PAGE);
  expect(screen.getByText("Order unknown")).toBeDefined();
  expect(screen.getByText("Quote of a legal title, not a request")).toBeDefined();
  expect(screen.getByText("Said after the first amendment")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Show more (3 left)" }));
  expect(screen.getAllByRole("article")).toHaveLength(total);
});

test("many credit holders are cut to the first rows until all are asked for", async () => {
  window.history.replaceState(null, "", `/lineage?law=${slug}`);
  const [first] = view.credits;
  if (first === undefined) {
    throw new Error("Fixture credit missing");
  }
  const credits = Array.from({ length: 20 }, (_, index) => ({
    ...first,
    holder_id: `actor:mep:${index}`,
    holder_kind: "mep" as const,
    name: `Member ${index}`,
    amendments: 20 - index,
    amendments_tabled: 20,
  }));
  serve({ ...view, credits });
  render(<LineagePage />);

  await openTab("Who");
  await screen.findByText("Member 0");
  expect(screen.queryByText("Member 19")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Show all 20" }));
  expect(screen.getByText("Member 19")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
  expect(screen.queryByText("Member 19")).toBeNull();
});

test("complete coverage is stated instead of left blank", async () => {
  window.history.replaceState(null, "", `/lineage?law=${slug}`);
  serve({
    ...view,
    coverage: view.coverage.map((row) => ({ ...row, status: "complete", reason: null })),
  });
  render(<LineagePage />);

  expect(
    await screen.findByText("Every source layer recorded for this law is complete."),
  ).toBeDefined();
});

test("a view whose records do not join is refused whole, and Reload asks again", async () => {
  window.history.replaceState(null, "", `/lineage?law=${slug}`);
  const fetchMock = serve({
    ...view,
    origins: [],
    adoptions: view.adoptions.map((adoption) => ({ ...adoption, phrase_ids: ["phrase:missing"] })),
  });
  render(<LineagePage />);

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain(
    "The lineage data for Artificial Intelligence Act is invalid",
  );
  expect(alert.textContent).toContain("names phrase:missing");
  expect(screen.queryByRole("article")).toBeNull();
  fireEvent.click(within(alert).getByRole("button", { name: "Reload law" }));
  await vi.waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(2));
});

test("an unknown adoption shows its reason and unknown counts, never zeros", async () => {
  const reason = "The final act was not collected";
  const unknown: LineageView = {
    ...view,
    status: "unknown",
    reason,
    counts: {
      ...view.counts,
      amendments_adopting: null,
      adopted_phrases: null,
      phrases_without_group: null,
      documents_read: null,
      documents_with_origin: null,
      changed_units: null,
      linked_units: null,
    },
    adopted_phrases: [],
    adoptions: [],
    origins: [],
    credits: [],
  };
  installFetch((path) => {
    if (path === "/api/v1/lineage") {
      return reply({
        laws: laws.laws.map((law) => ({
          ...law,
          status: "unknown",
          adopted_phrases: null,
          amendments_adopting: null,
          documents_with_origin: null,
        })),
      } satisfies LineageLawList);
    }
    return path === `/api/v1/lineage/${slug}` ? reply(unknown) : unexpected(path);
  });
  window.history.replaceState(null, "", `/lineage?law=${slug}`);
  render(<LineagePage />);

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain(`Adoption could not be computed for this law. ${reason}.`);
  const summary = screen.getByRole("region", { name: "From proposal to law" });
  expect(within(summary).getAllByText("unknown")).toHaveLength(3);
  expect(within(summary).getAllByText("Not counted in this run")).toHaveLength(3);
  expect(within(summary).queryByRole("img")).toBeNull();
  expect(await screen.findByText(/adoption unknown/)).toBeDefined();
});

test("an empty list says how to build the first lineage view and requests no law", async () => {
  const fetchMock = installFetch((path) =>
    path === "/api/v1/lineage" ? reply({ laws: [] } satisfies LineageLawList) : unexpected(path),
  );
  render(<LineagePage />);

  const empty = await screen.findByText(/No law has a lineage view yet/);
  expect(empty.textContent).toContain("make lineage LAW='2021/0106(COD)'");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("a law without a lineage view shows the backend's 404 detail", async () => {
  window.history.replaceState(null, "", "/lineage?law=2099-0003-COD");
  const detail = "No lineage view for 2099-0003-COD: run `make lineage LAW=...` for that law first";
  installFetch((path) => {
    if (path === "/api/v1/lineage") {
      return reply(laws);
    }
    return path === "/api/v1/lineage/2099-0003-COD" ? reply({ detail }, 404) : unexpected(path);
  });
  render(<LineagePage />);

  expect(
    await screen.findByRole("heading", { name: "No lineage view for 2099-0003-COD" }),
  ).toBeDefined();
  expect(screen.getByText(detail)).toBeDefined();
});

test("an unreachable API fails the law list and the law explicitly, and Retry recovers", async () => {
  window.history.replaceState(null, "", `/lineage?law=${slug}`);
  let listAttempts = 0;
  let lawAttempts = 0;
  installFetch((path) => {
    if (path === "/api/v1/lineage") {
      return listAttempts++ === 0 ? Promise.reject(new TypeError("Failed to fetch")) : reply(laws);
    }
    if (path === `/api/v1/lineage/${slug}`) {
      return lawAttempts++ === 0
        ? reply({ detail: "The lineage view is invalid" }, 500)
        : reply(view);
    }
    return unexpected(path);
  });
  render(<LineagePage />);

  expect(
    await screen.findByText(/The API could not be reached at \/api\/v1\/lineage\./),
  ).toBeDefined();
  expect(
    await screen.findByRole("heading", {
      name: `The lineage of ${slug} could not be loaded`,
    }),
  ).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Retry laws" }));
  fireEvent.click(screen.getByRole("button", { name: "Retry law" }));
  await openTab("Evidence");
  expect(await screen.findByRole("article", { name: /Phrase phrase:/ })).toBeDefined();
  expect(screen.getByRole("link", { name: "Atlas explorer" }).getAttribute("href")).toBe("/atlas");
});

test("choosing the open law again adds no history entry", async () => {
  window.history.replaceState(null, "", `/lineage?law=${slug}`);
  serve(view);
  render(<LineagePage />);

  const selector = await screen.findByRole("navigation", { name: "Collected laws" });
  fireEvent.click(
    await within(selector).findByRole("button", { name: /Artificial Intelligence Act/ }),
  );
  expect(window.history.pushState).not.toHaveBeenCalled();
});

test("clicking a graph node follows its paths and lists their evidence", async () => {
  window.history.replaceState(null, "", `/lineage?law=${slug}`);
  serve(view);
  render(<LineagePage />);

  await openTab("Graph");
  const heading = await screen.findByRole("heading", { name: /The graph: who/ });
  const section = heading.closest("section");
  if (section === null) {
    throw new Error("Graph section missing");
  }
  expect(within(section).queryByRole("article")).toBeNull();
  fireEvent.click(within(section).getByRole("button", { name: /Acme Unknown Lobby: 1 phrases/ }));
  expect(within(section).getByText(/Following/).textContent).toContain("Acme Unknown Lobby");
  expect(within(section).getAllByRole("article")).toHaveLength(1);
  fireEvent.click(within(section).getByRole("button", { name: "Back to the overview" }));
  expect(within(section).queryByRole("article")).toBeNull();
});

test("the Method tab walks the four steps with this law's own counts", async () => {
  serve(view);
  window.history.replaceState(null, "", `/lineage?law=${slug}`);
  render(<LineagePage />);

  await openTab("Method");
  const method = await screen.findByRole("region", { name: "How this analysis works" });
  expect(
    within(method)
      .getAllByRole("heading", { level: 4 })
      .map((h) => h.textContent),
  ).toEqual([
    "Compare the two texts",
    "Find the amendment",
    "Find who said it first",
    "Rank and check",
    "Where the data comes from",
  ]);
  expect(within(method).getByText("103 new words")).toBeDefined();
  expect(within(method).getByText("1 phrases from 1 amendments")).toBeDefined();
  expect(within(method).getByText("1 of 5 documents")).toBeDefined();
  expect(within(method).getByText("What this does not prove")).toBeDefined();
  const sources = within(method).getByRole("region", { name: "Where the data comes from" });
  expect(within(sources).getByText("8 proposal provisions")).toBeDefined();
  expect(within(sources).getByText("2 committee amendments")).toBeDefined();
  expect(within(sources).getByRole("link", { name: /Have Your Say/ })).toBeDefined();
});
