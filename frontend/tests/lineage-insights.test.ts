import { expect, test } from "vitest";
import { type LineagePhraseRow, prepareLineage } from "../lib/lineage";
import type { LineageView, OriginMatchRecord } from "../lib/lineage-api";
import {
  anyPhrase,
  drawLinks,
  filterPhrases,
  lineageChannels,
  linkPool,
  phraseFacets,
  rankOrganisations,
} from "../lib/lineage-insights";
import { fixtureView } from "./lineage-fixture";

const view = fixtureView();
const [origin] = view.origins;
const [adoption] = view.adoptions;
const [phrase] = view.adopted_phrases;
if (origin === undefined || adoption === undefined || phrase === undefined) {
  throw new Error("The lineage fixture lost its records");
}

function withOrigins(origins: OriginMatchRecord[]): LineageView {
  return { ...view, origins };
}

test("an organisation's phrase counts once however many of its documents say it", () => {
  const ranking = rankOrganisations(
    withOrigins([origin, { ...origin, document_id: "doc:hys_feedback:9" }]),
  );
  expect(ranking.rows).toEqual([
    {
      key: origin.actor_id,
      name: "Acme Unknown Lobby",
      adoptedFirst: 1,
      adoptedFirstLexical: 1,
      adoptedFirstSemantic: 0,
      adoptedOther: 0,
      tabledOnly: 0,
      reworded: 0,
      documents: 2,
      firstSaid: origin.published_at,
    },
  ]);
});

test("organisations rank by wording said first, and citations and unnamed stay apart", () => {
  const later: OriginMatchRecord = {
    ...origin,
    document_id: "doc:hys_feedback:5",
    actor_id: null,
    organisation: "Beta Association",
    published_at: null,
    precedes: false,
    eligibility: "amendment_first",
  };
  const ranking = rankOrganisations(
    withOrigins([
      later,
      origin,
      { ...origin, document_id: "doc:hys_feedback:6", organisation: null, actor_id: null },
      { ...origin, document_id: "doc:hys_feedback:7", is_citation: true },
    ]),
  );
  expect(ranking.rows.map((row) => [row.name, row.adoptedFirst, row.adoptedOther])).toEqual([
    ["Acme Unknown Lobby", 1, 0],
    ["Beta Association", 0, 1],
  ]);
  expect(ranking.rows[1]?.key).toBe("name:Beta Association");
  expect(ranking.rows[1]?.firstSaid).toBeNull();
  expect(ranking.unnamedDocuments).toBe(1);
  expect(ranking.citations).toBe(1);
});

test("a phrase found only reworded is counted as reworded; one also found verbatim is not", () => {
  const semantic: OriginMatchRecord = { ...origin, kind: "semantic", similarity: 0.8 };
  const alone = rankOrganisations(withOrigins([semantic])).rows[0];
  expect([alone?.reworded, alone?.adoptedFirstLexical, alone?.adoptedFirstSemantic]).toEqual([
    1, 0, 1,
  ]);
  expect(rankOrganisations(withOrigins([semantic, origin])).rows[0]?.reworded).toBe(0);
});

test("channels count each amendment once and split matches by their dates", () => {
  const twice = { ...adoption, kind: "semantic" as const };
  const plenary = {
    ...adoption,
    amendment_id: "am:2021-0106-COD:PLEN:1",
    stage: "plenary" as const,
    committee: null,
    author_groups: ["EPP", null],
    author_ids: ["actor:mep:1", "actor:mep:2"],
    tabled_on: null,
  };
  const channels = lineageChannels({
    ...view,
    adoptions: [adoption, twice, plenary],
    origins: [
      origin,
      { ...origin, eligibility: "amendment_first", precedes: false },
      { ...origin, eligibility: "unknown_date", precedes: null, kind: "semantic" },
      { ...origin, is_citation: true },
    ],
  });
  expect(channels.adoptingAmendments).toBe(2);
  expect(channels.byStage).toEqual([
    { label: "committee", count: 1 },
    { label: "plenary", count: 1 },
  ]);
  expect(channels.byCommittee.map((row) => row.label)).toEqual(["Committee unknown", "ENVI"]);
  expect(channels.byYear).toEqual([
    { label: "2022", count: 1 },
    { label: "Date unknown", count: 1 },
  ]);
  // The fixture amendment's two Members are both S&D: one group is not a coalition.
  expect(channels.crossGroup).toBe(0);
  expect(channels.withGroup).toBe(2);
  expect(channels.timing).toEqual({
    askFirst: 1,
    amendmentFirst: 1,
    unknownDate: 1,
    citation: 1,
  });
  expect([channels.verbatimMatches, channels.rewordedMatches]).toEqual([3, 1]);
  const coalition = lineageChannels({
    ...view,
    adoptions: [{ ...adoption, author_groups: ["S&D", "Renew"] }],
  });
  expect(coalition.crossGroup).toBe(1);
});

function rows(count: number): readonly LineagePhraseRow[] {
  const [row] = prepareLineage(view).adopted;
  if (row === undefined) {
    throw new Error("The fixture has no adopted phrase");
  }
  return Array.from({ length: count }, (_, index) => ({ ...row, phraseId: `phrase:${index}` }));
}

test("search matches every word across quotes, Members and organisations, ignoring accents", () => {
  const adopted = prepareLineage(view).adopted;
  expect(filterPhrases(adopted, { ...anyPhrase, query: "ACME six months" })).toHaveLength(1);
  expect(filterPhrases(adopted, { ...anyPhrase, query: "cesar luena" })).toHaveLength(1);
  expect(filterPhrases(adopted, { ...anyPhrase, query: "acme biometric" })).toHaveLength(0);
  expect(filterPhrases(adopted, { ...anyPhrase, group: "S&D" })).toHaveLength(1);
  expect(filterPhrases(adopted, { ...anyPhrase, group: "EPP" })).toHaveLength(0);
  expect(filterPhrases(adopted, { ...anyPhrase, committee: "ITRE" })).toHaveLength(0);
  expect(filterPhrases(adopted, { ...anyPhrase, evidence: "first" })).toHaveLength(1);
  expect(filterPhrases(adopted, { ...anyPhrase, evidence: "reworded" })).toHaveLength(0);
  expect(filterPhrases(adopted, { ...anyPhrase, evidence: "lexical" })).toHaveLength(1);
  expect(phraseFacets(adopted)).toEqual({ groups: ["S&D"], committees: ["ENVI"] });
});

test("only adopted phrases a submission said first can be drawn", () => {
  const lineage = prepareLineage(withOrigins([]));
  expect(linkPool(lineage.adopted)).toHaveLength(0);
  expect(linkPool(prepareLineage(view).adopted)).toHaveLength(1);
});

test("a draw is distinct, bounded by the pool, and repeated by its seed", () => {
  const pool = rows(50);
  for (let seed = 0; seed < 200; seed += 1) {
    const drawn = drawLinks(pool, 3, seed);
    expect(drawn, `seed ${seed}`).toHaveLength(3);
    expect(new Set(drawn.map((row) => row.phraseId)).size, `seed ${seed}`).toBe(3);
    expect(drawLinks(pool, 3, seed)).toEqual(drawn);
  }
  expect(drawLinks(rows(2), 3, 7)).toHaveLength(2);
  expect(drawLinks([], 3, 7)).toHaveLength(0);
  const seen = new Set(
    Array.from({ length: 200 }, (_, seed) => drawLinks(pool, 1, seed)[0]?.phraseId),
  );
  // Not a fixed pick: 200 seeds reach most of the 50 phrases.
  expect(seen.size).toBeGreaterThan(40);
});
