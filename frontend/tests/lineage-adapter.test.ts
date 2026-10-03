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
  expect(phrase.text).toBe("for at least six months after the system is placed on the market");
  expect(only(phrase.finalQuotes).text).toBe(phrase.text);
  const amendment = only(phrase.amendments);
  expect(amendment.amendmentId).toBe("am:2021-0106-COD:ENVI:PE7-7");
  expect(amendment.authors).toContain("César Luena");
  expect([amendment.adoptedWords, amendment.insertedWords]).toEqual([13, 13]);
  const origin = only(phrase.origins);
  expect([origin.organisation, origin.precedes, origin.isCitation]).toEqual([
    "Acme Unknown Lobby",
    true,
    false,
  ]);
  expect(phrase.hasEarlierRequest).toBe(true);
  expect(prepared.tabled).toEqual([]);
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
      said("phrase:c", { precedes: false }),
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
