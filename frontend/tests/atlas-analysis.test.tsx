// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AtlasAnalysis, type AtlasAnalysisProps } from "../components/atlas-analysis";
import type { AtlasLawFindings } from "../lib/atlas-findings";

// Outside Next.js's router, the open law is read from jsdom's URL.
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(window.location.search),
}));

const source = { title: "Final act, Article 8", url: "https://example.org/act#article-8" };
const props: AtlasAnalysisProps = {
  sampleLabel: "Two sampled laws, 2021–2024",
  coverageNotes: ["Consultation submissions unavailable for one law."],
  rankings: [
    {
      actorId: "association",
      actor: "Example association",
      fullWins: 2,
      observedAsks: 10,
      assessedAsks: 6,
      partial: 1,
      notObserved: 3,
      unknown: 4,
      evidence: [
        {
          key: source.url,
          recordIds: ["art:act:article-8"],
          title: source.title,
          url: source.url,
          linkId: "link:association-1",
        },
      ],
    },
  ],
  findings: {
    WHO: [
      {
        id: "who-1",
        text: "The association has two fully reflected asks.",
        sources: [source],
        limitations: ["Only the observed sample is represented."],
      },
    ],
    WHAT: [],
    TOWARDS: [],
    HOW: [],
    NEXT: [],
  },
};
beforeEach(() => {
  window.history.replaceState(null, "", "/atlas");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("labels the observed sample and preserves full, partial and unknown counts separately", () => {
  render(<AtlasAnalysis {...props} />);
  expect(screen.getByText("Two sampled laws, 2021–2024")).toBeDefined();
  expect(screen.getByText("Consultation submissions unavailable for one law.")).toBeDefined();
  const row = screen.getByRole("row", { name: /Example association/ });
  expect(
    within(row)
      .getAllByRole("cell")
      .map((cell) => cell.textContent),
  ).toEqual([
    "Example association",
    "2 of 6 assessed",
    "10",
    "1",
    "3",
    "4",
    "Final act, Article 8",
  ]);
  expect(screen.getByRole("columnheader", { name: "Fully reflected, of assessed asks" }));
  expect(screen.queryByText(/too few to rank/)).toBeNull();
  expect(
    screen.getByText(
      /The denominator includes assessed outcomes, including partial outcomes, and excludes unknown/,
    ),
  ).toBeDefined();
  expect(screen.queryByText(/20%/)).toBeNull();
});

test("renders source-backed findings and separate gaps for every missing report section", () => {
  render(<AtlasAnalysis {...props} />);
  const who = screen.getByRole("region", { name: "WHO" });
  expect(within(who).getByText("The association has two fully reflected asks.")).toBeDefined();
  const link = within(who).getByRole("link", { name: source.title });
  expect(link.getAttribute("href")).toBe(source.url);
  expect(link.getAttribute("rel")).toBe("noreferrer");
  expect(within(who).getByText("Only the observed sample is represented.")).toBeDefined();
  for (const section of ["WHAT", "TOWARDS", "HOW"]) {
    expect(
      within(screen.getByRole("region", { name: section })).getByText(
        "Evidence gap: no source-backed finding supplied.",
      ),
    ).toBeDefined();
  }
  expect(
    screen.getByText("Forecast unavailable: no source-backed forecast supplied."),
  ).toBeDefined();
});

test.each([
  { sources: [] },
  { sources: [{ title: "Unsafe citation", url: "javascript:alert(1)" }] },
  { sources: [{ title: "Broken citation", url: "not a URL" }] },
])("withholds findings without a usable public citation (%j)", ({ sources }) => {
  render(
    <AtlasAnalysis
      {...props}
      findings={{
        ...props.findings,
        HOW: [
          {
            id: "unsupported",
            text: "A private meeting caused the change.",
            sources,
            limitations: [],
          },
        ],
      }}
    />,
  );
  const how = screen.getByRole("region", { name: "HOW" });
  expect(within(how).queryByText("A private meeting caused the change.")).toBeNull();
  expect(within(how).queryByRole("link")).toBeNull();
  expect(
    within(how).getByText("Evidence gap: supplied finding has no usable public source."),
  ).toBeDefined();
});

test("keeps zero sample, missing ranking evidence, and missing coverage explicit", () => {
  const row = props.rankings[0];
  if (!row) {
    throw new Error("Ranking fixture missing");
  }
  const { rerender } = render(
    <AtlasAnalysis
      {...props}
      coverageNotes={[]}
      rankings={[
        {
          ...row,
          fullWins: 0,
          observedAsks: 0,
          assessedAsks: 0,
          partial: 0,
          notObserved: 0,
          unknown: 0,
          evidence: [],
        },
      ]}
    />,
  );
  expect(screen.getByText("Coverage information unavailable.")).toBeDefined();
  expect(
    screen.getByRole("cell", {
      name: "Rate unavailable · 0 full wins; 0 assessed asks too few to rank (fewer than 3 assessed)",
    }),
  ).toBeDefined();
  expect(screen.queryByText(/0 of 0/)).toBeNull();
  expect(screen.getByText("No evidence records supplied for this row.")).toBeDefined();
  rerender(<AtlasAnalysis {...props} rankings={[]} />);
  expect(screen.getByText("Rankings unavailable: no observed sample supplied.")).toBeDefined();
});

test("displays only a supplied forecast and its limitations without inventing a probability", () => {
  render(
    <AtlasAnalysis
      {...props}
      findings={{
        ...props.findings,
        NEXT: [
          {
            id: "next-1",
            text: "Supplied model forecast for an open ask.",
            sources: [source],
            limitations: ["Validation covers only two held-out laws."],
          },
        ],
      }}
    />,
  );
  const next = screen.getByRole("region", { name: "NEXT" });
  expect(within(next).getByText("Supplied model forecast for an open ask.")).toBeDefined();
  expect(within(next).getByText("Validation covers only two held-out laws.")).toBeDefined();
  expect(within(next).queryByText(/Forecast unavailable/)).toBeNull();
  expect(next.textContent).not.toContain("%");
});

test("all-unknown outcomes leave the rate unavailable rather than showing zero wins", () => {
  const row = props.rankings[0];
  if (!row) {
    throw new Error("Ranking fixture missing");
  }
  render(
    <AtlasAnalysis
      {...props}
      rankings={[
        {
          ...row,
          fullWins: 0,
          assessedAsks: 0,
          observedAsks: 4,
          partial: 0,
          notObserved: 0,
          unknown: 4,
        },
      ]}
    />,
  );
  const displayed = screen.getByRole("row", { name: /Example association/ });
  expect(
    within(displayed)
      .getAllByRole("cell")
      .map((cell) => cell.textContent),
  ).toEqual([
    "Example association",
    "Rate unavailable · 0 full wins; 0 assessed asks too few to rank (fewer than 3 assessed)",
    "4",
    "0",
    "0",
    "4",
    "Final act, Article 8",
  ]);
  expect(displayed.textContent).not.toContain("0%");
  expect(displayed.textContent).not.toContain("0 / 4");
});

const slug = "2021-0106-COD";
const findingsPath = `/api/v1/atlas/${slug}/findings`;
const noFindings: AtlasAnalysisProps["findings"] = {
  WHO: [],
  WHAT: [],
  TOWARDS: [],
  HOW: [],
  NEXT: [],
};
const lawFindings: AtlasLawFindings = {
  schema_version: "findings-1",
  procedure_id: "2021/0106(COD)",
  slug,
  title: "Artificial Intelligence Act",
  run_id: "20261003T120000Z",
  findings: [
    {
      question: "WHO",
      title: "WHO wins",
      status: "computed",
      headline: "0 of 3 actors with asks have at least 3 assessed final-act outcomes.",
      details: ["Lineage: 0 of 3 amendments (`data/laws/2021-0106-COD/lineage.json`)."],
      evidence: [
        { file: "data/laws/2021-0106-COD/atlas.json", field: "rankings" },
        { file: "data/laws/2021-0106-COD/lineage.json", field: null },
      ],
      limitation: "wins count only outcomes traced through published links.",
      command: null,
      notes: [],
    },
    {
      question: "WHAT",
      title: "WHAT they win",
      status: "computed",
      headline: "0 of 85 new words of the final act trace to a tabled amendment.",
      details: [],
      evidence: [],
      limitation: "shared wording is text reuse.",
      command: null,
      notes: ["Not run: `data/laws/2021-0106-COD/coordinated.json` is missing."],
    },
    {
      question: "HOW",
      title: "HOW they win",
      status: "not_run",
      headline: null,
      details: [],
      evidence: [],
      limitation: "these are channels associated with the law, not causes of its wording.",
      command: "make channels LAW='2021/0106(COD)'",
      notes: ["Not run: `data/laws/2021-0106-COD/channels.json` is missing."],
    },
    {
      question: "NEXT",
      title: "NEXT",
      status: "not_run",
      headline: null,
      details: [],
      evidence: [],
      limitation: "a forecast is published as a probability only after a backtest.",
      command: null,
      notes: [],
    },
  ],
};

function reply(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function serveFindings(respond: () => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path !== findingsPath) {
      throw new Error(`Unexpected request: ${path}`);
    }
    return respond();
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

test("renders each card from the findings endpoint: headline, evidence, limitation, not run", async () => {
  window.history.replaceState(null, "", `/atlas?law=${slug}`);
  const fetchMock = serveFindings(() => reply(lawFindings));
  render(<AtlasAnalysis {...props} findings={noFindings} />);

  expect(screen.getByRole("status").textContent).toBe("Loading the report's findings…");
  const who = screen.getByRole("region", { name: "WHO" });
  expect(await within(who).findByText(/^0 of 3 actors with asks/)).toBeDefined();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(
    within(who).getByText(
      "Evidence: data/laws/2021-0106-COD/atlas.json, field rankings; data/laws/2021-0106-COD/lineage.json",
    ),
  ).toBeDefined();
  expect(within(who).getByText("1 more line")).toBeDefined();
  expect(
    within(who).getByText("Lineage: 0 of 3 amendments (data/laws/2021-0106-COD/lineage.json)."),
  ).toBeDefined();
  expect(
    within(who).getByText("Limitation: wins count only outcomes traced through published links."),
  ).toBeDefined();
  expect(who.textContent).not.toContain("`");

  const what = screen.getByRole("region", { name: "WHAT" });
  expect(within(what).queryByText(/^Evidence:/)).toBeNull();
  expect(within(what).queryByText(/more line/)).toBeNull();
  expect(
    within(what).getByText("Not run: data/laws/2021-0106-COD/coordinated.json is missing."),
  ).toBeDefined();

  const how = screen.getByRole("region", { name: "HOW" });
  expect(how.textContent).toContain("Not run yet: make channels LAW='2021/0106(COD)'");
  expect(how.textContent).not.toContain("Evidence gap");
  expect(screen.getByRole("region", { name: "NEXT" }).textContent).toContain(
    "Not run yet: no command recorded",
  );
  expect(
    within(screen.getByRole("region", { name: "TOWARDS" })).getByText(
      "Evidence gap: the backend sent no TOWARDS finding.",
    ),
  ).toBeDefined();
  expect(screen.queryByRole("status")).toBeNull();
});

test("a law that was never collected names the backend's reason in every card", async () => {
  window.history.replaceState(null, "", `/atlas?law=${slug}`);
  serveFindings(() => reply({ detail: "No collected bundle; run `make atlas LAW=...`" }, 404));
  render(<AtlasAnalysis {...props} findings={noFindings} />);

  const next = screen.getByRole("region", { name: "NEXT" });
  expect(
    await within(next).findByText("Not collected: No collected bundle; run make atlas LAW=..."),
  ).toBeDefined();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("a failed or malformed answer is an explicit error with a retry", async () => {
  window.history.replaceState(null, "", `/atlas?law=${slug}`);
  let answer: Response = reply({ detail: "boom" }, 500);
  const fetchMock = serveFindings(() => answer);
  render(<AtlasAnalysis {...props} findings={noFindings} />);

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("The Atlas API answered 500: boom");
  expect(
    within(screen.getByRole("region", { name: "HOW" })).getByText("Finding could not be loaded."),
  ).toBeDefined();

  answer = reply({ ...lawFindings, findings: [{ ...lawFindings.findings[0], status: "maybe" }] });
  fireEvent.click(within(alert).getByRole("button", { name: "Retry findings" }));
  expect((await screen.findByRole("alert")).textContent).toContain(
    "Invalid findings data: findings[0].status must be computed or not_run.",
  );
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("supplied findings still take precedence over the endpoint's", async () => {
  window.history.replaceState(null, "", `/atlas?law=${slug}`);
  serveFindings(() => reply(lawFindings));
  render(<AtlasAnalysis {...props} />);

  const who = screen.getByRole("region", { name: "WHO" });
  expect(within(who).getByText("The association has two fully reflected asks.")).toBeDefined();
  const how = screen.getByRole("region", { name: "HOW" });
  expect(await within(how).findByText(/Not run yet:/)).toBeDefined();
  expect(within(who).queryByText(/^0 of 3 actors/)).toBeNull();
});

test("a 1 of 1 row is an anecdote: shown as a count with a too-few-to-rank marker", () => {
  const row = props.rankings[0];
  if (!row) {
    throw new Error("Ranking fixture missing");
  }
  render(
    <AtlasAnalysis
      {...props}
      rankings={[
        {
          ...row,
          actorId: "acme",
          actor: "Acme Unknown Lobby",
          fullWins: 1,
          observedAsks: 1,
          assessedAsks: 1,
          partial: 0,
          notObserved: 0,
          unknown: 0,
        },
        { ...row, fullWins: 1, assessedAsks: 3 },
      ]}
    />,
  );
  const anecdote = screen.getByRole("row", { name: /Acme Unknown Lobby/ });
  expect(within(anecdote).getByText("1 of 1 assessed")).toBeDefined();
  expect(within(anecdote).getByText("too few to rank (fewer than 3 assessed)")).toBeDefined();
  expect(within(anecdote).queryByText(/1 \/ 1|100%/)).toBeNull();
  const ranked = screen.getByRole("row", { name: /Example association/ });
  expect(within(ranked).getByText("1 of 3 assessed")).toBeDefined();
  expect(within(ranked).queryByText(/too few to rank/)).toBeNull();
});

test("ranking evidence links each source, opens the actor's card, and names missing records", () => {
  const row = props.rankings[0];
  if (!row) {
    throw new Error("Ranking fixture missing");
  }
  const opened: string[] = [];
  const evidence = [
    ...row.evidence,
    {
      key: "doc:missing",
      recordIds: ["doc:missing", "passage:missing-1"],
      title: "doc:missing",
      url: null,
      linkId: null,
    },
    {
      key: "javascript:alert(1)",
      recordIds: ["doc:unsafe"],
      title: "Unsafe",
      url: "javascript:alert(1)",
      linkId: null,
    },
    ...["a", "b"].map((id) => ({
      key: `https://example.org/${id}`,
      recordIds: [`doc:${id}`],
      title: `Document ${id}`,
      url: `https://example.org/${id}`,
      linkId: null,
    })),
  ];
  const { rerender } = render(
    <AtlasAnalysis
      {...props}
      rankings={[{ ...row, evidence }]}
      onOpenEvidence={(linkId) => opened.push(linkId)}
    />,
  );
  const cell = within(screen.getByRole("row", { name: /Example association/ }));
  const link = cell.getByRole("link", { name: source.title });
  expect(link.getAttribute("href")).toBe(source.url);
  expect(link.getAttribute("title")).toBe("art:act:article-8");
  fireEvent.click(cell.getByRole("button", { name: "Open evidence card" }));
  expect(opened).toEqual(["link:association-1"]);
  expect(
    cell.getByText(
      "doc:missing, passage:missing-1: not in the loaded records; no source available.",
    ),
  ).toBeDefined();
  expect(cell.getByText("doc:unsafe: source link unavailable.")).toBeDefined();
  expect(cell.queryByRole("link", { name: "Unsafe" })).toBeNull();
  expect(cell.getByText("2 more sources")).toBeDefined();
  expect(cell.getAllByRole("link", { hidden: true }).map((item) => item.textContent)).toEqual([
    source.title,
    "Document a",
    "Document b",
  ]);
  rerender(<AtlasAnalysis {...props} rankings={[{ ...row, evidence }]} />);
  expect(screen.queryByRole("button", { name: "Open evidence card" })).toBeNull();
});
