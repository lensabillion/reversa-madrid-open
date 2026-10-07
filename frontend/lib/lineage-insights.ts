import type { LineagePhraseRow } from "./lineage";
import type { LineageView, OriginMatchRecord } from "./lineage-api";

/**
 * Aggregates of one lineage view that answer the brief's questions for a whole law: which
 * organisations said wording that reached the law (WHO), through which channels it got there
 * (HOW), and a reproducible random draw of published links for the jury's side-by-side check.
 * Every number is counted from the view's records; nothing here scores or ranks anew beyond
 * the stated sort order. Linear in the view's records, plus sorting the rows.
 */

/**
 * One organisation whose submission said, before any amendment carried it, wording that
 * amendments inserted. Only such matches count: wording said after the amendment, or
 * undated, cannot have shaped it.
 */
export interface OrganisationRow {
  /** The resolved actor when there is one, otherwise the name as the submission gives it. */
  key: string;
  name: string;
  /** Adopted phrases this organisation said before every amendment carrying them. */
  adoptedFirst: number;
  /** Of `adoptedFirst`: found word for word (lexical), and found only reworded (semantic). */
  adoptedFirstLexical: number;
  adoptedFirstSemantic: number;
  /** Phrases it said first that amendments inserted but the final act does not hold. */
  tabledOnly: number;
  /** Phrases found only by a reworded (semantic, Jev-judged) match, of all its phrases. */
  reworded: number;
  documents: number;
  /** The earliest publication date among its matching documents; `null` when all are undated. */
  firstSaid: string | null;
}

/** Origins with no organisation name: citizens or unnamed attachments, never given a name. */
export interface OrganisationRanking {
  rows: readonly OrganisationRow[];
  unnamedDocuments: number;
  /** Matches that quote another act or the proposal: shared wording, not a request. */
  citations: number;
  /** Matches dated after the first carrying amendment, or undated: not counted as influence. */
  notFirst: number;
}

interface OrganisationTally {
  name: string;
  adoptedFirst: Set<string>;
  adoptedFirstLexical: Set<string>;
  tabled: Set<string>;
  verbatim: Set<string>;
  semantic: Set<string>;
  documents: Set<string>;
  firstSaid: string | null;
}

function countsAsOrigin(origin: OriginMatchRecord): boolean {
  return origin.eligibility === "ask_first" && !origin.is_citation;
}

function earlier(left: string | null, right: string | null): string | null {
  if (left === null) {
    return right;
  }
  return right === null || left <= right ? left : right;
}

/**
 * Organisations ranked by adopted phrases they said first, then by other adopted phrases,
 * then by tabled ones; the name breaks ties so the order is the same on every render.
 * A phrase counts once per organisation however many of its documents say it.
 */
export function rankOrganisations(view: LineageView): OrganisationRanking {
  const adopted = new Set(view.adopted_phrases.map((phrase) => phrase.phrase_id));
  const tallies = new Map<string, OrganisationTally>();
  const unnamed = new Set<string>();
  let citations = 0;
  let notFirst = 0;
  for (const origin of view.origins) {
    if (origin.is_citation) {
      citations += 1;
      continue;
    }
    // Wording said after the amendment, or undated, cannot be shown to have shaped it.
    if (!countsAsOrigin(origin)) {
      notFirst += 1;
      continue;
    }
    if (origin.organisation === null) {
      unnamed.add(origin.document_id);
      continue;
    }
    const key = origin.actor_id ?? `name:${origin.organisation}`;
    const tally = tallies.get(key) ?? {
      name: origin.organisation,
      adoptedFirst: new Set<string>(),
      adoptedFirstLexical: new Set<string>(),
      tabled: new Set<string>(),
      verbatim: new Set<string>(),
      semantic: new Set<string>(),
      documents: new Set<string>(),
      firstSaid: null,
    };
    tallies.set(key, tally);
    tally.documents.add(origin.document_id);
    tally.firstSaid = earlier(tally.firstSaid, origin.published_at);
    (origin.kind === "semantic" ? tally.semantic : tally.verbatim).add(origin.phrase_id);
    if (!adopted.has(origin.phrase_id)) {
      tally.tabled.add(origin.phrase_id);
    } else {
      tally.adoptedFirst.add(origin.phrase_id);
      if (origin.kind === "verbatim") {
        tally.adoptedFirstLexical.add(origin.phrase_id);
      }
    }
  }
  const rows = [...tallies.entries()].map(
    ([key, tally]): OrganisationRow => ({
      key,
      name: tally.name,
      adoptedFirst: tally.adoptedFirst.size,
      adoptedFirstLexical: tally.adoptedFirstLexical.size,
      adoptedFirstSemantic: tally.adoptedFirst.size - tally.adoptedFirstLexical.size,
      tabledOnly: tally.tabled.size,
      reworded: [...tally.semantic].filter((id) => !tally.verbatim.has(id)).length,
      documents: tally.documents.size,
      firstSaid: tally.firstSaid,
    }),
  );
  rows.sort(
    (left, right) =>
      right.adoptedFirst - left.adoptedFirst ||
      right.tabledOnly - left.tabledOnly ||
      left.name.localeCompare(right.name) ||
      left.key.localeCompare(right.key),
  );
  return { rows, unnamedDocuments: unnamed.size, citations, notFirst };
}

/** How many of something, under one label; rows are sorted by count, then by label. */
export interface ChannelCount {
  label: string;
  count: number;
}

/** The routes adopted wording took, from the adoptions and origins of one view. */
export interface LineageChannels {
  /** Distinct amendments whose wording reached the final act. */
  adoptingAmendments: number;
  byStage: readonly ChannelCount[];
  byCommittee: readonly ChannelCount[];
  /** Adopting amendments tabled jointly by Members of at least two political groups. */
  crossGroup: number;
  /** Adopting amendments with at least one known political group. */
  withGroup: number;
  byYear: readonly ChannelCount[];
  /** Matches between a submission and inserted wording, by what their dates say. */
  timing: {
    askFirst: number;
    amendmentFirst: number;
    unknownDate: number;
    citation: number;
  };
  /** Matches by how they were found: identical words, or reworded and judged by Jev. */
  verbatimMatches: number;
  rewordedMatches: number;
}

function counted(values: Iterable<string>): ChannelCount[] {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
}

/** Channels of one view. An amendment adopted both verbatim and reworded counts once. */
export function lineageChannels(view: LineageView): LineageChannels {
  const amendments = new Map<string, LineageView["adoptions"][number]>();
  for (const adoption of view.adoptions) {
    if (!amendments.has(adoption.amendment_id)) {
      amendments.set(adoption.amendment_id, adoption);
    }
  }
  const adoptions = [...amendments.values()];
  let crossGroup = 0;
  let withGroup = 0;
  for (const adoption of adoptions) {
    const groups = new Set(adoption.author_groups.filter((group) => group !== null));
    withGroup += groups.size > 0 ? 1 : 0;
    crossGroup += groups.size >= 2 ? 1 : 0;
  }
  const timing = { askFirst: 0, amendmentFirst: 0, unknownDate: 0, citation: 0 };
  let rewordedMatches = 0;
  for (const origin of view.origins) {
    rewordedMatches += origin.kind === "semantic" ? 1 : 0;
    if (origin.is_citation) {
      timing.citation += 1;
    } else if (origin.eligibility === "ask_first") {
      timing.askFirst += 1;
    } else if (origin.eligibility === "amendment_first") {
      timing.amendmentFirst += 1;
    } else {
      timing.unknownDate += 1;
    }
  }
  return {
    adoptingAmendments: adoptions.length,
    byStage: counted(adoptions.map((adoption) => adoption.stage)),
    byCommittee: counted(adoptions.map((adoption) => adoption.committee ?? "Committee unknown")),
    crossGroup,
    withGroup,
    byYear: counted(
      adoptions.map((adoption) => adoption.tabled_on?.slice(0, 4) ?? "Date unknown"),
    ).sort((left, right) => left.label.localeCompare(right.label)),
    timing,
    verbatimMatches: view.origins.length - rewordedMatches,
    rewordedMatches,
  };
}

/** What the phrase list can be narrowed to; an empty value means "any". */
export interface PhraseFilter {
  query: string;
  group: string;
  committee: string;
  /**
   * "first": a submission said it before the amendments; "lexical": a word-for-word match;
   * "reworded": a semantic match judged by Jev.
   */
  evidence: "" | "first" | "any-origin" | "lexical" | "reworded";
}

export const anyPhrase: PhraseFilter = { query: "", group: "", committee: "", evidence: "" };

function fold(text: string): string {
  return text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
}

/** Everything a reader may type to find a phrase: its words, quotes, amendments and sources. */
function haystack(phrase: LineagePhraseRow): string {
  return fold(
    [
      phrase.text,
      ...phrase.finalQuotes.map((span) => span.text),
      ...phrase.amendments.flatMap((amendment) => [
        amendment.amendmentId,
        amendment.committee ?? "",
        ...amendment.authors,
      ]),
      ...phrase.origins.flatMap((origin) => [origin.organisation ?? "", origin.quote.text]),
    ].join("\n"),
  );
}

/**
 * The phrases that pass every set filter. The query matches when every word of it appears,
 * ignoring case and accents. Linear in the phrases and their text.
 */
export function filterPhrases(
  phrases: readonly LineagePhraseRow[],
  filter: PhraseFilter,
): readonly LineagePhraseRow[] {
  const words = fold(filter.query).split(/\s+/u).filter(Boolean);
  return phrases.filter((phrase) => {
    if (filter.group !== "" && !phrase.amendments.some((a) => a.groups.includes(filter.group))) {
      return false;
    }
    if (
      filter.committee !== "" &&
      !phrase.amendments.some((a) => a.committee === filter.committee)
    ) {
      return false;
    }
    if (filter.evidence === "first" && !phrase.hasEarlierRequest) {
      return false;
    }
    if (filter.evidence === "any-origin" && phrase.origins.length === 0) {
      return false;
    }
    if (filter.evidence === "lexical" && !phrase.origins.some((o) => o.kind === "verbatim")) {
      return false;
    }
    if (filter.evidence === "reworded" && !phrase.origins.some((o) => o.kind === "semantic")) {
      return false;
    }
    if (words.length === 0) {
      return true;
    }
    const text = haystack(phrase);
    return words.every((word) => text.includes(word));
  });
}

/** The political groups and committees that carry at least one phrase, for the filter menus. */
export function phraseFacets(phrases: readonly LineagePhraseRow[]): {
  groups: readonly string[];
  committees: readonly string[];
} {
  const groups = new Set<string>();
  const committees = new Set<string>();
  for (const phrase of phrases) {
    for (const amendment of phrase.amendments) {
      for (const group of amendment.groups) {
        groups.add(group);
      }
      if (amendment.committee !== null) {
        committees.add(amendment.committee);
      }
    }
  }
  return {
    groups: [...groups].sort((a, b) => a.localeCompare(b)),
    committees: [...committees].sort((a, b) => a.localeCompare(b)),
  };
}

/**
 * A small seeded generator (mulberry32), so a draw of links can be repeated from its seed:
 * the jury's pick is reproducible, and a test can fix it.
 */
function generator(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * The phrases a published link can be drawn from: adopted wording that a submission said
 * word for word before the amendments, so the link reads submission → amendment → final
 * act. Semantic (Jev) matches are left out of the draw: word-for-word wording is the
 * strongest evidence, while a reworded match can pair the same safeguard on a different
 * object (on the AI Act, trade secrets in technical documentation, Art. 11, with personal
 * data in the sandbox, Art. 54(1)(g)).
 */
export function linkPool(adopted: readonly LineagePhraseRow[]): readonly LineagePhraseRow[] {
  return adopted.filter(
    (phrase) =>
      phrase.adopted &&
      phrase.origins.some((origin) => origin.countsAsOrigin && origin.kind === "verbatim"),
  );
}

/**
 * Draws `size` distinct phrases from `pool` with a partial Fisher–Yates shuffle seeded by
 * `seed`; the same seed always draws the same links. O(pool) time for the copy.
 */
export function drawLinks(
  pool: readonly LineagePhraseRow[],
  size: number,
  seed: number,
): readonly LineagePhraseRow[] {
  const random = generator(seed);
  const items = [...pool];
  const taken = Math.min(size, items.length);
  for (let index = 0; index < taken; index += 1) {
    const pick = index + Math.floor(random() * (items.length - index));
    const chosen = items[pick];
    const current = items[index];
    if (chosen === undefined || current === undefined) {
      throw new Error("The link draw went out of range");
    }
    items[index] = chosen;
    items[pick] = current;
  }
  return items.slice(0, taken);
}

/** One step of the summary funnel: `part` of `whole`, or a lone count when `whole` is null. */
export interface FunnelStep {
  id: "proposal" | "final" | "traced" | "amendments" | "documents";
  part: number | null;
  /** `null` when the step has no total to compare with (the two texts' provision counts). */
  whole: number | null;
  /** Extra counts the step's sentence quotes, `null` when not counted. */
  detail: number | null;
  /**
   * For the documents step: documents with a word-for-word origin, and documents whose only
   * origins are reworded (Jev-judged), so the two add up to the documents with an origin.
   */
  split: { lexical: number; semantic: number } | null;
}

function provisions(view: LineageView, layer: "proposal" | "final_act"): number | null {
  const row = view.coverage.find((item) => item.layer === layer);
  return row === undefined || row.status !== "complete" ? null : row.count;
}

/**
 * The law's lineage as five steps a newcomer reads top to bottom: the proposal's provisions,
 * the final act's provisions and its new words, the new words traced to amendments (in how
 * many adopted phrases), the amendments that carry them, and the consultation documents that
 * said that wording first (from how many named organisations). Only counts already in the
 * view and its eligible adopted-origin records; nothing is estimated.
 */
export function lineageFunnel(
  view: LineageView,
  ranking: OrganisationRanking,
): readonly FunnelStep[] {
  const { counts } = view;
  const documentsKnown =
    view.status !== "unknown" &&
    counts.documents_read !== null &&
    counts.documents_with_origin !== null;
  const adopted = new Set(view.adopted_phrases.map((phrase) => phrase.phrase_id));
  const kinds = new Map<string, Set<OriginMatchRecord["kind"]>>();
  for (const origin of view.origins) {
    if (adopted.has(origin.phrase_id) && countsAsOrigin(origin)) {
      const seen = kinds.get(origin.document_id) ?? new Set();
      seen.add(origin.kind);
      kinds.set(origin.document_id, seen);
    }
  }
  const lexical = [...kinds.values()].filter((seen) => seen.has("verbatim")).length;
  return [
    { id: "proposal", part: provisions(view, "proposal"), whole: null, detail: null, split: null },
    {
      id: "final",
      part: provisions(view, "final_act"),
      whole: null,
      detail: counts.changed_units,
      split: null,
    },
    {
      id: "traced",
      part: counts.linked_units,
      whole: counts.changed_units,
      detail: counts.adopted_phrases,
      split: null,
    },
    {
      id: "amendments",
      part: counts.amendments_adopting,
      whole: counts.amendments,
      detail: null,
      split: null,
    },
    {
      id: "documents",
      part: documentsKnown ? kinds.size : null,
      whole: counts.documents_read,
      detail: documentsKnown ? ranking.rows.filter((row) => row.adoptedFirst > 0).length : null,
      split: documentsKnown ? { lexical, semantic: kinds.size - lexical } : null,
    },
  ];
}
