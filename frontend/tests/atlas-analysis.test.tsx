// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { AtlasAnalysis, type AtlasAnalysisProps } from "../components/atlas-analysis";

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
      sources: [source],
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
afterEach(cleanup);

test("labels the observed sample and preserves full, partial and unknown counts separately", () => {
  render(<AtlasAnalysis {...props} />);
  expect(screen.getByText("Two sampled laws, 2021–2024")).toBeDefined();
  expect(screen.getByText("Consultation submissions unavailable for one law.")).toBeDefined();
  const row = screen.getByRole("row", { name: /Example association/ });
  expect(
    within(row)
      .getAllByRole("cell")
      .map((cell) => cell.textContent),
  ).toEqual(["Example association", "2 / 6", "10", "1", "3", "4", "Final act, Article 8"]);
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
          sources: [],
        },
      ]}
    />,
  );
  expect(screen.getByText("Coverage information unavailable.")).toBeDefined();
  expect(
    screen.getByRole("cell", { name: "Rate unavailable · 0 full wins; 0 assessed asks" }),
  ).toBeDefined();
  expect(screen.queryByText("0 / 0")).toBeNull();
  expect(screen.getByText("Source evidence unavailable.")).toBeDefined();
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
    "Rate unavailable · 0 full wins; 0 assessed asks",
    "4",
    "0",
    "0",
    "4",
    "Final act, Article 8",
  ]);
  expect(displayed.textContent).not.toContain("0%");
  expect(displayed.textContent).not.toContain("0 / 4");
});
