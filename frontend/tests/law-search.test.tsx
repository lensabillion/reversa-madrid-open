// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { BUILD_POLL_MS, LawSearch } from "../components/law-search";
import type { BuildState, LawHit } from "../lib/law-search";

function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function hit(overrides: Partial<LawHit> = {}): LawHit {
  return {
    procedure_id: "2021/0106(COD)",
    title: "Artificial Intelligence Act",
    slug: "2021-0106-COD",
    has_lineage: false,
    has_atlas: false,
    build: null,
    ...overrides,
  };
}

function buildState(state: BuildState["state"], overrides: Partial<BuildState> = {}): BuildState {
  return {
    slug: "2021-0106-COD",
    procedure_id: "2021/0106(COD)",
    state,
    step: state === "running" ? "lineage" : null,
    steps: ["lineage"],
    started_at: "2026-10-03T10:00:00Z",
    finished_at: state === "done" || state === "failed" ? "2026-10-03T10:01:00Z" : null,
    error: state === "failed" ? "Parltrack dump missing" : null,
    log: [`log ${state}`],
    ...overrides,
  };
}

function found(law: LawHit) {
  return { query: "AI Act", status: "found", law, choices: [], message: null };
}

/** Each call answers with the next response; requests are recorded as "METHOD path". */
function serve(responses: Response[]) {
  const calls: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    calls.push(`${init?.method ?? "GET"} ${url.pathname}`);
    const next = responses.shift();
    if (next === undefined) {
      throw new Error(`Unexpected request: ${url.pathname}`);
    }
    return next;
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

async function flush(ms = 0) {
  const completion = act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
  await Promise.resolve(completion);
}

async function searchFor(text: string) {
  fireEvent.change(screen.getByLabelText("Search any EU law"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await flush();
}

function setup(view: "lineage" | "atlas" = "lineage") {
  const onOpen = vi.fn();
  const onBuilt = vi.fn();
  const rendered = render(<LawSearch view={view} onOpen={onOpen} onBuilt={onBuilt} />);
  return { onOpen, onBuilt, rendered };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("a found law that is built for this page links to Open", async () => {
  serve([reply(found(hit({ has_atlas: true })))]);
  const { onOpen } = setup("atlas");
  await searchFor("AI Act");
  expect(screen.getByText("Artificial Intelligence Act")).toBeTruthy();
  const open = screen.getByRole("link", { name: "Open" });
  expect(open.getAttribute("href")).toBe("?law=2021-0106-COD");
  fireEvent.click(open);
  expect(onOpen).toHaveBeenCalledWith("2021-0106-COD");
  expect(screen.queryByRole("button", { name: "Build it now" })).toBeNull();
});

test("a found law without a build is built and polled until done", async () => {
  const calls = serve([
    reply(found(hit({ has_atlas: true }))),
    reply(buildState("queued"), 202),
    reply(buildState("running")),
    reply(buildState("done")),
  ]);
  const { onBuilt } = setup("lineage");
  await searchFor("AI Act");
  fireEvent.click(screen.getByRole("button", { name: "Build it now" }));
  await flush();
  expect(screen.getByText("Build queued")).toBeTruthy();
  expect(calls[1]).toBe("POST /api/v1/laws/2021-0106-COD/build");
  await flush(BUILD_POLL_MS);
  expect(screen.getByText("Build running: lineage")).toBeTruthy();
  expect(screen.getByText("log running")).toBeTruthy();
  expect(onBuilt).not.toHaveBeenCalled();
  await flush(BUILD_POLL_MS);
  expect(onBuilt).toHaveBeenCalledExactlyOnceWith("2021-0106-COD");
  await flush(BUILD_POLL_MS * 3);
  expect(calls).toHaveLength(4);
});

test("a failed build shows its error and can be tried again", async () => {
  const calls = serve([
    reply(found(hit())),
    reply(buildState("running"), 202),
    reply(buildState("failed")),
    reply(buildState("queued"), 202),
  ]);
  const { onBuilt } = setup();
  await searchFor("AI Act");
  fireEvent.click(screen.getByRole("button", { name: "Build it now" }));
  await flush();
  await flush(BUILD_POLL_MS);
  expect(screen.getByText("Parltrack dump missing")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await flush();
  expect(screen.getByText("Build queued")).toBeTruthy();
  expect(calls[3]).toBe("POST /api/v1/laws/2021-0106-COD/build");
  expect(onBuilt).not.toHaveBeenCalled();
});

test("ambiguous answers list choices that pick one law", async () => {
  serve([
    reply({
      query: "data",
      status: "ambiguous",
      law: null,
      choices: [
        hit({ slug: "a", title: "Data Act" }),
        hit({ slug: "b", title: "Data Governance Act", has_lineage: true }),
      ],
      message: "Several laws match.",
    }),
  ]);
  setup();
  await searchFor("data");
  expect(screen.getByText("Several laws match.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Data Governance Act/ }));
  expect(screen.getByRole("link", { name: "Open" }).getAttribute("href")).toBe("?law=b");
});

test("not_found shows the backend's message", async () => {
  serve([
    reply({
      query: "zzz",
      status: "not_found",
      law: null,
      choices: [],
      message: "No law matches zzz.",
    }),
  ]);
  setup();
  await searchFor("zzz");
  expect(screen.getByText("No law matches zzz.")).toBeTruthy();
});

test("a missing catalog (503) shows its detail", async () => {
  serve([reply({ detail: "Run make setup first." }, 503)]);
  setup();
  await searchFor("AI Act");
  expect(screen.getByRole("alert").textContent).toBe("Run make setup first.");
});

test("a build refused with 409 shows its detail", async () => {
  serve([reply(found(hit())), reply({ detail: "Another build is running." }, 409)]);
  setup();
  await searchFor("AI Act");
  fireEvent.click(screen.getByRole("button", { name: "Build it now" }));
  await flush();
  expect(screen.getByText("Another build is running.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
});

test("an empty query is not sent", async () => {
  const calls = serve([]);
  setup();
  await searchFor("   ");
  expect(screen.getByRole("alert").textContent).toBe("Type a law to search for.");
  expect(calls).toHaveLength(0);
});

test("a malformed answer is reported, not repaired", async () => {
  serve([reply({ query: "x", status: "found", law: null, choices: [], message: null })]);
  setup();
  await searchFor("x");
  expect(screen.getByRole("alert").textContent).toContain("LawSearch.law is missing");
});

test("unmounting stops polling", async () => {
  const calls = serve([reply(found(hit({ build: buildState("running") })))]);
  const { rendered } = setup();
  await searchFor("AI Act");
  expect(screen.getByText("Build running: lineage")).toBeTruthy();
  rendered.unmount();
  await flush(BUILD_POLL_MS * 3);
  expect(calls).toHaveLength(1);
});
