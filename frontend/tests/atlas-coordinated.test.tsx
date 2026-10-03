// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AtlasCoordinated, type AtlasCoordinatedState } from "../components/atlas-coordinated";
import {
  type AtlasClusterMember,
  type AtlasCoordinatedCluster,
  type AtlasCoordinatedView,
  coordinatedView,
} from "../lib/atlas-coordinated";

afterEach(cleanup);

const procedure = "2099/0001(COD)";

function member(number: number, fields: Partial<AtlasClusterMember> = {}): AtlasClusterMember {
  const id = `am:2099-0001-COD:IMCO:PE1.001-${number}`;
  return {
    amendment_id: id,
    stage: "committee",
    committee: "IMCO",
    tabled_on: "2099-03-31",
    target_provision: "Proposal for a regulation - Article 8 – paragraph 1",
    author_ids: [`actor:mep:${number}`],
    author_names: [`Member ${number}`],
    political_groups: ["PPE"],
    inserted: [
      { record_id: id, field: "new_text", page: null, start: 10, end: 50, text: "keep the logs" },
    ],
    ...fields,
  };
}

function cluster(
  number: number,
  fields: Partial<AtlasCoordinatedCluster> = {},
): AtlasCoordinatedCluster {
  return {
    cluster_id: `coord:2099-0001-COD:IMCO:PE1.001-${number}`,
    members: [member(number * 10 + 1), member(number * 10 + 2)],
    political_groups: ["PPE"],
    cross_group: false,
    inserted_words: 14,
    min_similarity: 0.9,
    ...fields,
  };
}

const spanning = cluster(1, {
  members: [
    member(11, {
      author_names: ["Ada Alfa", "Bo Beta"],
      political_groups: ["PPE", "Renew"],
      inserted: [
        {
          record_id: "am:2099-0001-COD:IMCO:PE1.001-11",
          field: "new_text",
          page: null,
          start: 0,
          end: 20,
          text: "providers shall keep",
        },
        {
          record_id: "am:2099-0001-COD:IMCO:PE1.001-11",
          field: "new_text",
          page: null,
          start: 30,
          end: 60,
          text: "logs for at least six months",
        },
      ],
    }),
    member(12, {
      committee: null,
      tabled_on: null,
      target_provision: null,
      author_names: [],
      political_groups: [],
      stage: "plenary",
    }),
  ],
  political_groups: ["PPE", "Renew", "S&D"],
  cross_group: true,
  inserted_words: 23,
  min_similarity: 1,
});
const view: AtlasCoordinatedView = {
  schema_version: "atlas-1",
  procedure_id: procedure,
  slug: "2099-0001-COD",
  title: "Fixture Regulation on widget safety",
  run_id: "20991201T090000Z",
  generated_at: "2099-12-01T09:00:00Z",
  method: "shingle-jaccard-1",
  min_inserted_words: 12,
  shingle_words: 5,
  similarity_threshold: 0.8,
  counts: { amendments: 5660, compared: 2967, too_short: 2684, not_comparable: 9 },
  // Supplied order differs from id order: the panel must keep it.
  clusters: [spanning, cluster(3), cluster(2)],
  limitations: [
    "Near-identical wording tabled by Members of different groups is consistent with a shared outside draft. It does not show who wrote the draft.",
    "Both numbers are proposed, not calibrated.",
  ],
};

function panel(state: Partial<AtlasCoordinatedState>) {
  return (
    <AtlasCoordinated
      procedureId={procedure}
      state={{ data: null, error: null, retry: () => undefined, ...state }}
    />
  );
}
const found = (shown: AtlasCoordinatedView) => panel({ data: { found: true, view: shown } });

test("states the headline counts and lists clusters in the supplied order", () => {
  render(found(view));
  const region = screen.getByRole("region", { name: "Coordinated amendments" });
  expect(
    within(region).getByRole("heading", { name: "Coordinated amendments", level: 2 }),
  ).toBeDefined();
  expect(within(region).getByText("1 of 3 clusters span political groups")).toBeDefined();
  expect(
    within(region).getByText(
      "2,967 of 5,660 amendments compared · 2,684 too short (under 12 inserted words) · 9 not comparable",
    ),
  ).toBeDefined();
  expect(
    within(region).getByText(
      "Method shingle-jaccard-1: 5-word runs, similarity threshold 0.8. Run 20991201T090000Z, generated 2099-12-01T09:00:00Z.",
    ),
  ).toBeDefined();
  const clusters = within(screen.getByRole("list", { name: "Clusters" })).getAllByRole("article");
  expect(clusters).toHaveLength(3);
  expect(
    // The first amendment of each cluster.
    clusters.map((item) => within(item).getAllByText(/^am:/)[0]?.textContent),
  ).toEqual([
    "am:2099-0001-COD:IMCO:PE1.001-11",
    "am:2099-0001-COD:IMCO:PE1.001-31",
    "am:2099-0001-COD:IMCO:PE1.001-21",
  ]);
  expect(region.textContent).not.toMatch(/ghost|wrote the amendment|authored by a lobby/i);
});

test("a cluster shows its groups, size and each member's details with the wording quoted exactly", () => {
  render(found(view));
  const first = screen.getByRole("article", { name: "Cluster 1" });
  expect(within(first).getByText("Spans political groups")).toBeDefined();
  expect(
    within(within(first).getByRole("list", { name: "Political groups in this cluster" }))
      .getAllByRole("listitem")
      .map((chip) => chip.textContent),
  ).toEqual(["PPE", "Renew", "S&D"]);
  expect(
    within(first).getByText(
      "2 amendments · at least 23 inserted words each · least similar pair 1.00",
    ),
  ).toBeDefined();
  const members = within(
    within(first).getByRole("list", { name: "Amendments of cluster 1" }),
  ).getAllByRole("listitem");
  const [known, unknown] = members.filter((item) => item.querySelector("blockquote") !== null);
  if (known === undefined || unknown === undefined) {
    throw new Error("Both members must render");
  }
  expect(known.textContent).toContain("IMCO · committee stage · tabled 2099-03-31");
  expect(known.textContent).toContain("Tabled by Ada Alfa, Bo Beta");
  expect(known.textContent).toContain("Proposal for a regulation - Article 8 – paragraph 1");
  expect(known.querySelector("blockquote")?.textContent).toBe(
    "providers shall keep … logs for at least six months",
  );
  expect(
    within(within(known).getByRole("list", { name: "Political groups of the authors" }))
      .getAllByRole("listitem")
      .map((chip) => chip.textContent),
  ).toEqual(["PPE", "Renew"]);
  // Unknown values are named as unknown; none is left blank or shown as an empty group.
  expect(unknown.textContent).toContain(
    "Committee not recorded · plenary stage · tabling date unknown",
  );
  expect(unknown.textContent).toContain(
    "Political groups of the authors: unknown (not in the Member data)",
  );
  expect(unknown.textContent).toContain("Tabled by authors not recorded");
  expect(unknown.textContent).toContain("Target provision not recorded");
  expect(unknown.querySelector("blockquote")?.textContent).toBe("keep the logs");

  const second = screen.getByRole("article", { name: "Cluster 2" });
  expect(within(second).getByText("Not marked as spanning groups")).toBeDefined();
});

test("expanding a cluster lays its members side by side, and collapsing stacks them again", () => {
  render(found(view));
  const first = screen.getByRole("article", { name: "Cluster 1" });
  const members = within(first).getByRole("list", { name: "Amendments of cluster 1" });
  const toggle = within(first).getByRole("button", { name: "Compare side by side" });
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  expect(members.className).not.toContain("grid-flow-col");

  fireEvent.click(toggle);
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  expect(toggle.textContent).toBe("Stack the amendments");
  expect(members.className).toContain("grid-flow-col");
  // Only the chosen cluster changes.
  expect(
    within(screen.getByRole("article", { name: "Cluster 2" }))
      .getByRole("button", { name: "Compare side by side" })
      .getAttribute("aria-expanded"),
  ).toBe("false");

  fireEvent.click(toggle);
  expect(members.className).not.toContain("grid-flow-col");
});

test("limitations are shown verbatim, and their absence is stated", () => {
  render(found(view));
  const limits = screen.getByRole("region", { name: "Limits of this method" });
  expect(
    within(limits)
      .getAllByRole("listitem")
      .map((item) => item.textContent),
  ).toEqual(view.limitations);
  cleanup();
  render(found({ ...view, limitations: [] }));
  expect(
    screen.getByText("The pipeline supplied no limitations for this cluster file."),
  ).toBeDefined();
});

test("a long list is drawn in pages of 25 that keep the supplied order", () => {
  const many = Array.from({ length: 30 }, (_, index) => cluster(index + 1));
  render(found({ ...view, clusters: many }));
  expect(screen.getAllByRole("article")).toHaveLength(25);
  expect(screen.getByText(/Showing 25 of 30\./)).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Show 5 more clusters" }));
  expect(screen.getAllByRole("article")).toHaveLength(30);
  expect(screen.queryByRole("button", { name: /more clusters/ })).toBeNull();
  expect(screen.getByRole("article", { name: "Cluster 30" }).textContent).toContain(
    "am:2099-0001-COD:IMCO:PE1.001-301",
  );
});

test("a file without clusters says so with its counts and still shows the limits", () => {
  render(
    found({
      ...view,
      clusters: [],
      counts: { amendments: 40, compared: 1, too_short: 39, not_comparable: 0 },
    }),
  );
  expect(screen.getByText("0 of 0 clusters span political groups")).toBeDefined();
  expect(screen.getByText(/No clusters: among the 1 amendment compared/)).toBeDefined();
  expect(screen.queryByRole("list", { name: "Clusters" })).toBeNull();
  expect(screen.getByRole("region", { name: "Limits of this method" })).toBeDefined();
});

test("loading is announced and shows no count", () => {
  render(panel({}));
  expect(screen.getByRole("status").textContent).toBe("Loading coordinated amendments…");
  expect(screen.queryByText(/clusters? spans? political groups/)).toBeNull();
});

test("a law without a cluster file says so, as unknown, with the command for this law", () => {
  render(panel({ data: { found: false, detail: "No coordinated amendments for 2099-0001-COD." } }));
  const region = screen.getByRole("region", { name: "Coordinated amendments" });
  expect(within(region).getByText("This law has no cluster file yet.")).toBeDefined();
  expect(within(region).getByText("No coordinated amendments for 2099-0001-COD.")).toBeDefined();
  expect(region.textContent).toContain("That is unknown, not zero");
  expect(region.textContent).toContain("make atlas LAW='2099/0001(COD)'");
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.queryByText(/of \d+ clusters/)).toBeNull();
});

test("a failed request shows its message and Retry calls back", () => {
  const retry = vi.fn();
  render(panel({ error: "The Atlas API answered 500: Failure", retry }));
  const failure = screen.getByRole("alert");
  expect(within(failure).getByText("The Atlas API answered 500: Failure")).toBeDefined();
  expect(screen.queryByRole("list", { name: "Clusters" })).toBeNull();
  fireEvent.click(within(failure).getByRole("button", { name: "Retry coordinated amendments" }));
  expect(retry).toHaveBeenCalledTimes(1);
});

test("the boundary check returns a valid response unchanged", () => {
  expect(coordinatedView(JSON.parse(JSON.stringify(view)))).toEqual(view);
});

const wire = (change: (body: Record<string, unknown>) => void): unknown => {
  const body = JSON.parse(JSON.stringify(view)) as Record<string, unknown>;
  change(body);
  return body;
};
const firstCluster = (body: Record<string, unknown>) =>
  (body.clusters as Record<string, unknown>[])[0] as Record<string, unknown>;
const firstMember = (body: Record<string, unknown>) =>
  (firstCluster(body).members as Record<string, unknown>[])[0] as Record<string, unknown>;

test.each([
  { fault: "a list instead of an object", body: [], message: "the response must be an object" },
  {
    fault: "another schema",
    body: wire((body) => {
      body.schema_version = "atlas-2";
    }),
    message: "Unsupported coordinated amendments schema: atlas-2",
  },
  {
    fault: "a missing count",
    body: wire((body) => {
      body.counts = { amendments: 1, compared: 1, too_short: 0 };
    }),
    message: "counts.not_comparable must be a non-negative integer",
  },
  {
    fault: "a cluster of one amendment",
    body: wire((body) => {
      firstCluster(body).members = [firstMember(body)];
    }),
    message: "clusters[0].members must be a list of at least 2",
  },
  {
    fault: "a cross_group that is not a boolean",
    body: wire((body) => {
      firstCluster(body).cross_group = "yes";
    }),
    message: "clusters[0].cross_group must be true or false",
  },
  {
    fault: "a similarity above 1",
    body: wire((body) => {
      firstCluster(body).min_similarity = 1.2;
    }),
    message: "clusters[0].min_similarity must be a number from 0 to 1",
  },
  {
    fault: "a member without inserted wording",
    body: wire((body) => {
      firstMember(body).inserted = [];
    }),
    message: "clusters[0].members[0].inserted must be a list of at least 1",
  },
  {
    fault: "a span without text",
    body: wire((body) => {
      firstMember(body).inserted = [
        { record_id: "am:x", field: "new_text", page: null, start: 0, end: 1 },
      ];
    }),
    message: "clusters[0].members[0].inserted[0].text must be a non-empty string",
  },
  {
    fault: "an unknown span field",
    body: wire((body) => {
      firstMember(body).inserted = [
        { record_id: "am:x", field: "title", page: null, start: 0, end: 1, text: "a" },
      ];
    }),
    message: "clusters[0].members[0].inserted[0].field must be a source field",
  },
  {
    fault: "a numeric committee",
    body: wire((body) => {
      firstMember(body).committee = 7;
    }),
    message: "clusters[0].members[0].committee must be a string or null",
  },
  {
    fault: "limitations that are not text",
    body: wire((body) => {
      body.limitations = [1];
    }),
    message: "limitations[0] must be a string",
  },
])("the boundary check rejects $fault", ({ body, message }) => {
  expect(() => coordinatedView(body)).toThrow(message);
});
