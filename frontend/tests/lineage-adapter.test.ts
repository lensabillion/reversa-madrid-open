import { expect, test } from "vitest";
import { prepareLineage } from "../lib/lineage";
import type { LineageView, OriginMatchRecord } from "../lib/lineage-api";
import { fixtureView } from "./lineage-fixture";

function only<T>(rows: readonly T[]): T {
  expect(rows).toHaveLength(1);
  const row = rows[0];
  if (row === undefined) {
    throw new Error("Row missing");
  }
  return row;
}

test("joins an adopted phrase with its final quotation, amendment and earlier submission", () => {
  const view = fixtureView();

  const prepared = prepareLineage(view);

  const phrase = only(prepared.adopted);
  expect(phrase.text).toBe(
    "providers shall keep the logs for at least six months after the system is placed on the market",
  );
  expect(only(phrase.finalQuotes).text).toBe(
    "Providers shall keep the logs for at least six months after the system is placed on the market",
  );
  const amendment = only(phrase.amendments);
  expect(amendment.amendmentId).toBe("am:2021-0106-COD:ENVI:PE7-7");
  // The test world's amendment names three people but resolves two IDs, so no group is attached.
  expect(amendment.authors).toContain("César Luena");
  expect([amendment.adoptedWords, amendment.newWords]).toEqual([18, 18]);
  const origin = only(phrase.origins);
  expect([origin.organisation, origin.precedes, origin.isCitation, origin.countsAsOrigin]).toEqual([
    "Acme Unknown Lobby",
    true,
    false,
    true,
  ]);
  expect([phrase.hasEarlierRequest, phrase.joint]).toEqual([true, true]);
  expect(prepared.tabled).toEqual([]);
});

test("authors carry their group only when names and IDs line up one to one", () => {
  const view = fixtureView();
  const adoption = only(view.adoptions);
  const paired: LineageView = {
    ...view,
    adoptions: [
      {
        ...adoption,
        author_names: ["Brando Benifei", "Margrete Auken"],
        author_groups: ["S&D", null],
      },
    ],
  };

  const amendment = only(only(prepareLineage(paired).adopted).amendments);

  expect(amendment.authors).toEqual(["Brando Benifei (S&D)", "Margrete Auken"]);
  const unnamed: LineageView = {
    ...view,
    adoptions: [{ ...adoption, author_names: [], author_groups: [] }],
  };
  expect(only(only(prepareLineage(unnamed).adopted).amendments).authors).toEqual(
    adoption.author_ids,
  );
});

test("only a dated, earlier, non-citation document counts as an origin", () => {
  const view = fixtureView();
  const origin = only(view.origins);
  const with_ = (changes: Partial<OriginMatchRecord>) =>
    only(only(prepareLineage({ ...view, origins: [{ ...origin, ...changes }] }).adopted).origins)
      .countsAsOrigin;

  expect(with_({})).toBe(true);
  expect(with_({ is_citation: true })).toBe(false);
  expect(with_({ precedes: false, eligibility: "amendment_first" })).toBe(false);
  expect(with_({ precedes: null, eligibility: "unknown_date" })).toBe(false);
});

test("splits credits into groups and holders and keeps the backend's order", () => {
  const view = fixtureView();

  const table = only(prepareLineage(view).credits);

  expect(table.basis).toBe("verbatim");
  const ids = (group: boolean) =>
    view.credits
      .filter((credit) => (credit.holder_kind === "group") === group)
      .map((credit) => credit.holder_id);
  expect(table.groups.map((row) => row.holderId)).toEqual(ids(true));
  expect(table.holders.map((row) => row.holderId)).toEqual(ids(false));
  expect(table.groups.length).toBeGreaterThan(0);
  expect(table.holders.length).toBeGreaterThan(0);
  const [first] = view.credits;
  expect(table.holders[0]).toEqual({
    holderId: first?.holder_id,
    kind: first?.holder_kind,
    name: first?.name,
    phrases: first?.phrases,
    jointPhrases: first?.joint_phrases,
    amendments: first?.amendments,
    amendmentsTabled: first?.amendments_tabled,
  });
});

test("tabled wording carries its amendments by id and its submissions", () => {
  const view = fixtureView();
  const adopted = only(view.adopted_phrases);
  const tabledView: LineageView = {
    ...view,
    adopted_phrases: [],
    adoptions: [],
    credits: [],
    tabled_phrases: [
      {
        phrase_id: adopted.phrase_id,
        text: adopted.text,
        words: adopted.words,
        amendment_ids: ["am:2021-0106-COD:ENVI:PE7-7"],
      },
    ],
  };

  const prepared = prepareLineage(tabledView);

  const phrase = only(prepared.tabled);
  expect([phrase.adopted, phrase.finalQuotes]).toEqual([false, []]);
  expect(only(phrase.amendments).stage).toBeNull();
  expect(only(phrase.origins).documentId).toBe("doc:hys_feedback:4");
  expect(prepared.credits).toEqual([]);
});

test("orders phrases by evidence: an earlier request first, then any submission, then length", () => {
  const view = fixtureView();
  const origin = only(view.origins);
  const phrase = (id: string, words: number) => ({
    phrase_id: id,
    text: Array.from({ length: words }, (_, index) => `w${index}`).join(" "),
    words,
    amendment_ids: ["am:1"],
  });
  const said = (id: string, changes: Partial<OriginMatchRecord>): OriginMatchRecord => ({
    ...origin,
    phrase_id: id,
    amendment_ids: ["am:1"],
    ...changes,
  });
  const prepared = prepareLineage({
    ...view,
    adopted_phrases: [],
    adoptions: [],
    credits: [],
    tabled_phrases: [
      phrase("phrase:a", 30),
      phrase("phrase:b", 9),
      phrase("phrase:c", 12),
      phrase("phrase:d", 12),
      phrase("phrase:e", 20),
    ],
    origins: [
      said("phrase:b", { precedes: true }),
      said("phrase:c", { precedes: false, eligibility: "amendment_first" }),
      said("phrase:e", { precedes: true, is_citation: true }),
    ],
  });

  expect(prepared.tabled.map((row) => row.phraseId)).toEqual([
    "phrase:b",
    "phrase:e",
    "phrase:c",
    "phrase:a",
    "phrase:d",
  ]);
});

test("refuses a view whose records name what it does not hold", () => {
  const view = fixtureView();
  const adoption = only(view.adoptions);
  const origin = only(view.origins);

  expect(() =>
    prepareLineage({ ...view, schema_version: "lineage-2" as unknown as "lineage-1" }),
  ).toThrow("Unsupported lineage view schema: lineage-2");
  expect(() =>
    prepareLineage({ ...view, adoptions: [{ ...adoption, phrase_ids: ["phrase:missing"] }] }),
  ).toThrow("names phrase:missing, which the view does not list");
  expect(() =>
    prepareLineage({ ...view, origins: [{ ...origin, phrase_id: "phrase:missing" }] }),
  ).toThrow("names phrase:missing, which the view does not list");
  expect(() =>
    prepareLineage({ ...view, origins: [{ ...origin, amendment_ids: ["am:stranger"] }] }),
  ).toThrow("names am:stranger, which does not carry its phrase");
});
