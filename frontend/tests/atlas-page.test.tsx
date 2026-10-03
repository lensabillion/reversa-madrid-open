// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import AtlasPage from "../app/atlas/page";
import type { AtlasBundle } from "../lib/atlas";
import type {
  AtlasLawList,
  AtlasLayerCoverage,
  AtlasRanking,
  AtlasSnapshotRecord,
  AtlasView,
} from "../lib/atlas-api";

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

/** Committed fixtures are generated and validated by the authoritative Python contracts. */
function records<T>(name: string): T[] {
  return readFileSync(
    resolve(process.cwd(), "../backend/tests/fixtures/atlas", `${name}.jsonl`),
    "utf8",
  )
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as T);
}
function first<T>(rows: readonly T[]): T {
  const row = rows[0];
  if (row === undefined) {
    throw new Error("Fixture record missing");
  }
  return row;
}

const procedure = "2099/0001(COD)";
const slug = "2099-0001-COD";
const fixtureLaw = first(
  records<{ procedure_id: string; title: string; coverage: AtlasLayerCoverage[] }>("laws").filter(
    (law) => law.procedure_id === procedure,
  ),
);
const ofLaw = <T extends { procedure_id: string }>(rows: readonly T[]) =>
  rows.filter((row) => row.procedure_id === procedure);
const full: AtlasBundle = {
  laws: records("laws"),
  documents: records("documents"),
  documentTexts: records("document_texts"),
  passages: records("passages"),
  actors: records("actors"),
  asks: records("asks"),
  amendments: records("amendments"),
  articles: records("articles"),
  links: records("links"),
  outcomes: records("outcomes"),
};
// The backend sends one law and only published, unconfirmed and contradicted links.
const bundle: AtlasBundle = {
  ...full,
  laws: ofLaw(full.laws),
  passages: ofLaw(full.passages),
  asks: ofLaw(full.asks),
  amendments: ofLaw(full.amendments),
  articles: ofLaw(full.articles),
  links: ofLaw(full.links).filter((link) => link.status !== "insufficient_evidence"),
  outcomes: ofLaw(full.outcomes),
};
// Supplied order differs from both name order and win-rate order: the view must keep it.
const rankings: AtlasRanking[] = [
  {
    actor_id: "actor:tr:234567890123-45",
    actor_name: "Consumer Watch",
    observed_asks: 1,
    assessed_asks: 1,
    full: 0,
    partial: 0,
    not_observed: 1,
    unknown: 0,
    full_win_rate: 0,
    evidence_record_ids: ["outcome:a-ask-watch-final"],
  },
  {
    actor_id: "actor:tr:123456789012-34",
    actor_name: "Widget Makers Europe",
    observed_asks: 2,
    assessed_asks: 2,
    full: 2,
    partial: 0,
    not_observed: 0,
    unknown: 0,
    full_win_rate: 1,
    evidence_record_ids: ["outcome:a-ask-makers-final", "outcome:a-ask-undated-final"],
  },
  {
    actor_id: "actor:tr:345678901234-56",
    actor_name: "City Network",
    observed_asks: 1,
    assessed_asks: 1,
    full: 0,
    partial: 1,
    not_observed: 0,
    unknown: 0,
    full_win_rate: 0,
    evidence_record_ids: ["outcome:a-ask-city-final"],
  },
];
const view: AtlasView = {
  schema_version: "atlas-view-1",
  procedure_id: procedure,
  slug,
  title: fixtureLaw.title,
  run_id: "20991201T090000Z",
  generated_at: "2099-12-01T09:00:00Z",
  ask_method: "passage-v0",
  coverage: fixtureLaw.coverage,
  bundle,
  snapshot: first(records<AtlasSnapshotRecord>("graphs")),
  rankings,
  limitations: [
    "Ask extraction v0: each consultation passage is treated as one ask, so counts are passages, not distinct requests.",
    "Invented contract fixtures",
  ],
};
const laws: AtlasLawList = {
  laws: [
    {
      slug,
      procedure_id: procedure,
      title: fixtureLaw.title,
      run_id: view.run_id,
      published_links: 1,
    },
    {
      slug: "2099-0002-COD",
      procedure_id: "2099/0002(COD)",
      title: "Fixture Directive on gadget labelling",
      run_id: "20991201T090500Z",
      published_links: 12,
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

function requested(fetchMock: ReturnType<typeof installFetch>): string[] {
  return fetchMock.mock.calls.map(([input]) => String(input));
}

const unexpected = (path: string): never => {
  throw new Error(`Unexpected request: ${path}`);
};
const workspaceHeading = { name: "Whose requests appear in EU law?" };

/** The graph also names the law, so selector buttons are found inside the selector. */
async function findLaw(name: RegExp): Promise<HTMLElement> {
  const selector = await screen.findByRole("navigation", { name: "Collected laws" });
  return within(selector).findByRole("button", { name });
}

beforeEach(() => {
  window.history.replaceState(null, "", "/atlas");
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

test("lists collected laws, opens one into the URL and renders its real atlas-1 records", async () => {
  const fetchMock = installFetch((path) => {
    if (path === "/api/v1/atlas") {
      return reply(laws);
    }
    return path === `/api/v1/atlas/${slug}` ? reply(view) : unexpected(path);
  });
  render(<AtlasPage />);

  expect(screen.getByRole("status").textContent).toBe("Loading collected laws…");
  const law = await findLaw(/Fixture Regulation on widget safety/);
  expect(law.textContent).toContain("2099/0001(COD) · 1 published link");
  expect(
    within(screen.getByRole("navigation", { name: "Collected laws" })).getByRole("button", {
      name: /gadget labelling/,
    }).textContent,
  ).toContain("2099/0002(COD) · 12 published links");
  expect(law.getAttribute("aria-pressed")).toBe("false");
  expect(screen.getByRole("heading", { name: "Choose a law" })).toBeDefined();
  expect(requested(fetchMock)).toEqual(["/api/v1/atlas"]);

  fireEvent.click(law);
  expect(window.location.search).toBe(`?law=${slug}`);
  expect(await screen.findByRole("heading", workspaceHeading)).toBeDefined();
  expect(requested(fetchMock)).toEqual(["/api/v1/atlas", `/api/v1/atlas/${slug}`]);
  expect(law.getAttribute("aria-pressed")).toBe("true");
  expect(
    screen.getByText(
      "Ask extraction method: passage-v0. Ask extraction v0: each consultation passage is treated as one ask, so counts are passages, not distinct requests. Invented contract fixtures.",
    ),
  ).toBeDefined();
  expect(
    screen.getByText(/Atlas run 20991201T090000Z, generated 2099-12-01T09:00:00Z/),
  ).toBeDefined();
  const layers = screen.getByRole("region", { name: "Source layers" });
  expect(within(layers).getByText("Committee amendments")).toBeDefined();
  expect(within(layers).getByText("1 of 5 submissions has no publication date")).toBeDefined();
  expect(within(layers).queryByText(/No links can be shown|no link was published/)).toBeNull();

  // The backend snapshot drives the real graph, and its link opens the bundle's evidence.
  fireEvent.click(
    screen.getByRole("button", {
      name: "Keep logs for at least six months echoed in IMCO amendment 101",
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Read source texts side by side →" }));
  const evidence = screen.getByRole("article", { name: "Atlas link evidence" });
  expect(
    within(evidence).getByRole("heading", { name: "Keep logs for at least six months" }),
  ).toBeDefined();
  expect(within(evidence).getByText("Published link")).toBeDefined();
  expect(screen.getByRole("status").textContent).toBe("1 of 1 published links shown");
  const coverage = screen.getByRole("complementary", { name: "Source coverage" });
  expect(
    within(coverage)
      .getAllByRole("listitem")
      .map((item) => item.textContent),
  ).toEqual([
    "Plenary amendments: missing from the source. None were tabled.",
    "Asks: partly collected. 1 of 5 submissions has no publication date.",
    "Actors: partly collected. 1 name matches two register entries.",
    "Meetings: not collected in this run. Connector not built.",
    "Votes: not collected in this run. Connector not built.",
  ]);
  fireEvent.click(screen.getByRole("button", { name: "Audit candidates" }));
  expect(screen.getByRole("status").textContent).toBe("3 of 3 audit candidates shown");

  fireEvent.click(screen.getByRole("button", { name: "See the outcomes" }));
  expect(
    screen.getByRole("heading", {
      name: "Fixture Regulation on widget safety, 2099/0001(COD): final-act outcomes of Atlas run 20991201T090000Z",
    }),
  ).toBeDefined();
  const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
  expect(rows.map((row) => row.querySelector("td")?.textContent)).toEqual([
    "Consumer Watch",
    "Widget Makers Europe",
    "City Network",
  ]);
  expect(rows[1]?.textContent).toContain("2 / 2");
  expect(
    within(screen.getByRole("table")).getAllByText("Source evidence unavailable."),
  ).toHaveLength(3);
  for (const section of ["WHO", "WHAT", "TOWARDS", "HOW"]) {
    expect(
      within(screen.getByRole("region", { name: section })).getByText(
        "Evidence gap: no source-backed finding supplied.",
      ),
    ).toBeDefined();
  }
  expect(
    within(screen.getByRole("region", { name: "NEXT" })).getByText(
      "Forecast unavailable: no source-backed forecast supplied.",
    ),
  ).toBeDefined();
});

test("a failed consultation collection is explained on the opening graph, not only in other tabs", async () => {
  window.history.replaceState(null, "", `/atlas?law=${slug}`);
  const reason =
    "Have Your Say could not be reached: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed";
  const failed: AtlasView = {
    ...view,
    coverage: view.coverage.map((row) =>
      row.layer === "asks" ? { ...row, status: "missing", count: 0, reason } : row,
    ),
    bundle: { ...bundle, links: [], outcomes: [] },
    // The pipeline's graph for a law without links: the law node alone.
    snapshot: {
      ...view.snapshot,
      nodes: view.snapshot.nodes.filter((node) => node.kind === "procedure"),
      edges: [],
    },
    rankings: [],
  };
  installFetch((path) => {
    if (path === "/api/v1/atlas") {
      return reply(laws);
    }
    return path === `/api/v1/atlas/${slug}` ? reply(failed) : unexpected(path);
  });
  render(<AtlasPage />);

  const layers = await screen.findByRole("region", { name: "Source layers" });
  expect(
    screen.getByRole("button", { name: "Explore the graph" }).getAttribute("aria-pressed"),
  ).toBe("true");
  expect(within(layers).getAllByRole("listitem")).toHaveLength(view.coverage.length);
  const asks = within(layers)
    .getAllByRole("listitem")
    .find((item) => item.textContent?.startsWith("Consultation feedback"));
  expect(asks?.textContent).toBe(`Consultation feedback · missing · 0Reason: ${reason}`);
  expect(
    within(layers).getByText(
      `No links can be shown because consultation feedback is missing: ${reason}.`,
    ),
  ).toBeDefined();
  expect(screen.getByRole("region", { name: "Influence graph" })).toBeDefined();
});

test("a shared link reopens its law, and choosing it again adds no history entry", async () => {
  window.history.replaceState(null, "", `/atlas?law=${slug}`);
  const fetchMock = installFetch((path) => {
    if (path === "/api/v1/atlas") {
      return reply(laws);
    }
    return path === `/api/v1/atlas/${slug}` ? reply(view) : unexpected(path);
  });
  render(<AtlasPage />);

  expect(await screen.findByRole("heading", workspaceHeading)).toBeDefined();
  const law = await findLaw(/Fixture Regulation on widget safety/);
  expect(law.getAttribute("aria-pressed")).toBe("true");
  fireEvent.click(law);
  expect(window.history.pushState).not.toHaveBeenCalled();
  expect(requested(fetchMock).sort()).toEqual(["/api/v1/atlas", `/api/v1/atlas/${slug}`]);
});

test("complete coverage and absent limitations are stated, not left blank", async () => {
  window.history.replaceState(null, "", `/atlas?law=${slug}`);
  const complete: AtlasView = {
    ...view,
    coverage: view.coverage.map((row) => ({ ...row, status: "complete", reason: null })),
    limitations: [],
  };
  installFetch((path) => {
    if (path === "/api/v1/atlas") {
      return reply(laws);
    }
    return path === `/api/v1/atlas/${slug}` ? reply(complete) : unexpected(path);
  });
  render(<AtlasPage />);

  expect(
    await screen.findByText(
      "Ask extraction method: passage-v0. The pipeline supplied no limitations for this run.",
    ),
  ).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "See the outcomes" }));
  expect(screen.getByText("Every source layer recorded for this law is complete.")).toBeDefined();
  expect(screen.queryByText("Coverage information unavailable.")).toBeNull();
});

test("an empty list says how to build the first Atlas and requests no law", async () => {
  const fetchMock = installFetch((path) =>
    path === "/api/v1/atlas" ? reply({ laws: [] } satisfies AtlasLawList) : unexpected(path),
  );
  render(<AtlasPage />);

  const empty = await screen.findByText(/No law has an Atlas run yet/);
  expect(empty.textContent).toContain("make atlas LAW='2021/0106(COD)'");
  expect(screen.queryByRole("heading", { name: "Choose a law" })).toBeNull();
  expect(screen.queryByRole("heading", workspaceHeading)).toBeNull();
  expect(requested(fetchMock)).toEqual(["/api/v1/atlas"]);
});

test("a law without an Atlas run shows the backend's 404 detail instead of a workspace", async () => {
  window.history.replaceState(null, "", "/atlas?law=2099-0003-COD");
  installFetch((path) => {
    if (path === "/api/v1/atlas") {
      return reply(laws);
    }
    return path === "/api/v1/atlas/2099-0003-COD"
      ? reply({ detail: "No Atlas run for 2099/0003(COD)." }, 404)
      : unexpected(path);
  });
  render(<AtlasPage />);

  const missing = await screen.findByRole("alert");
  expect(
    within(missing).getByRole("heading", { name: "No Atlas run for 2099-0003-COD" }),
  ).toBeDefined();
  expect(within(missing).getByText("No Atlas run for 2099/0003(COD).")).toBeDefined();
  expect(missing.textContent).toContain("make atlas LAW='2021/0106(COD)'");
  expect(screen.queryByRole("heading", workspaceHeading)).toBeNull();
});

test("an unreachable API fails the law list explicitly, and Retry recovers", async () => {
  let attempts = 0;
  installFetch((path) => {
    if (path === "/api/v1/atlas" && attempts++ === 0) {
      return Promise.reject(new TypeError("Failed to fetch"));
    }
    return path === "/api/v1/atlas" ? reply(laws) : unexpected(path);
  });
  render(<AtlasPage />);

  const failure = await screen.findByRole("alert");
  expect(failure.textContent).toContain("The Atlas API could not be reached at /api/v1/atlas.");
  fireEvent.click(within(failure).getByRole("button", { name: "Retry laws" }));
  expect(await findLaw(/Fixture Regulation on widget safety/)).toBeDefined();
  expect(screen.queryByRole("alert")).toBeNull();
});

test.each([
  {
    failure: "a validation detail list",
    respond: () =>
      reply(
        {
          detail: [
            { loc: ["path", "slug"], msg: "String should match pattern", type: "string_pattern" },
          ],
        },
        422,
      ),
    message: "The Atlas API answered 422: String should match pattern",
  },
  {
    failure: "a response without a JSON detail",
    respond: () => new Response("Internal Server Error", { status: 500, statusText: "Failure" }),
    message: "The Atlas API answered 500: Failure",
  },
  {
    failure: "a network failure",
    respond: () => Promise.reject(new TypeError("Failed to fetch")),
    message: `The Atlas API could not be reached at /api/v1/atlas/${slug}.`,
  },
])(
  "a law request with $failure shows its message, and Retry recovers",
  async ({ respond, message }) => {
    window.history.replaceState(null, "", `/atlas?law=${slug}`);
    let attempts = 0;
    installFetch((path) => {
      if (path === "/api/v1/atlas") {
        return reply(laws);
      }
      if (path !== `/api/v1/atlas/${slug}`) {
        return unexpected(path);
      }
      return attempts++ === 0 ? respond() : reply(view);
    });
    render(<AtlasPage />);

    const failure = await screen.findByRole("alert");
    expect(within(failure).getByText(message)).toBeDefined();
    expect(screen.queryByRole("heading", workspaceHeading)).toBeNull();
    fireEvent.click(within(failure).getByRole("button", { name: "Retry law" }));
    expect(await screen.findByRole("heading", workspaceHeading)).toBeDefined();
  },
);

test.each([
  {
    fault: "a quote that differs from its source text",
    body: {
      ...view,
      bundle: {
        ...bundle,
        links: bundle.links.map((link) =>
          link.link_id === "link:a-am1-makers"
            ? {
                ...link,
                ask_spans: link.ask_spans.map((span) => ({
                  ...span,
                  text: "for at least seven months",
                })),
              }
            : link,
        ),
      },
    },
    message: "Invalid source quote: doc:hys_feedback:9000001.text",
  },
  {
    fault: "an unknown view schema",
    body: { ...view, schema_version: "atlas-view-2" },
    message: "Unsupported Atlas view schema: atlas-view-2",
  },
])(
  "a view with $fault is reported as a data error with no evidence shown",
  async ({ body, message }) => {
    window.history.replaceState(null, "", `/atlas?law=${slug}`);
    installFetch((path) => {
      if (path === "/api/v1/atlas") {
        return reply(laws);
      }
      return path === `/api/v1/atlas/${slug}` ? reply(body) : unexpected(path);
    });
    render(<AtlasPage />);

    const failure = await screen.findByRole("alert");
    expect(
      within(failure).getByRole("heading", {
        name: "The Atlas data for Fixture Regulation on widget safety is invalid",
      }),
    ).toBeDefined();
    expect(within(failure).getByText(message)).toBeDefined();
    expect(screen.queryByRole("heading", workspaceHeading)).toBeNull();
    expect(screen.queryByRole("region", { name: "Influence graph" })).toBeNull();
    expect(screen.queryByText(/Keep logs for at least six months/)).toBeNull();
  },
);
