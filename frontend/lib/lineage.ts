import type { AtlasSourceSpan } from "./atlas";
import type {
  AmendmentAdoptionRecord,
  CreditRecord,
  LineageHolderKind,
  LineageMatchKind,
  LineageView,
  OriginMatchRecord,
} from "./lineage-api";

/** An amendment that carries a phrase; adoption details exist only for adopted wording. */
export interface LineageAmendmentRow {
  amendmentId: string;
  stage: "committee" | "plenary" | null;
  committee: string | null;
  /** Each author's name, with the political group in brackets when it is known. */
  authors: readonly string[];
  tabledOn: string | null;
  /** Words of the amendment's new text inside adopted wording, of all its words; `null` for tabled wording. */
  adoptedWords: number | null;
  newWords: number | null;
}

/** A submission that says the phrase, with the exact quotation and its date order. */
export interface LineageOriginRow {
  documentId: string;
  /** `null` for a citizen or an unnamed attachment: the explorer never invents a name. */
  organisation: string | null;
  publishedAt: string | null;
  quote: AtlasSourceSpan;
  words: number;
  precedes: boolean | null;
  isCitation: boolean;
  /** Dated before every carrying amendment and not a citation: the backend's `counts_as_origin`. */
  countsAsOrigin: boolean;
  kind: LineageMatchKind;
}

/** One phrase with every record that cites it, ready to show side by side. */
export interface LineagePhraseRow {
  phraseId: string;
  adopted: boolean;
  kind: LineageMatchKind;
  /** Folded words; the quotations keep the original casing and punctuation. */
  text: string;
  words: number;
  finalQuotes: readonly AtlasSourceSpan[];
  amendments: readonly LineageAmendmentRow[];
  origins: readonly LineageOriginRow[];
  /** At least one origin counts: a dated document that came first and is not a citation. */
  hasEarlierRequest: boolean;
  /** Credited to more than one holder. */
  joint: boolean;
}

export interface LineageCreditRow {
  holderId: string;
  kind: LineageHolderKind;
  name: string;
  /** Whole phrases credited (no fractional credit), and how many are shared. */
  phrases: number;
  jointPhrases: number;
  /** Amendments that reached the final act, of those tabled on this law. */
  amendments: number;
  amendmentsTabled: number;
}

export interface LineageCreditTable {
  basis: LineageMatchKind;
  groups: readonly LineageCreditRow[];
  /** Members, unresolved author names and the committee's own text, in the backend's order. */
  holders: readonly LineageCreditRow[];
}

export interface PreparedLineage {
  adopted: readonly LineagePhraseRow[];
  tabled: readonly LineagePhraseRow[];
  credits: readonly LineageCreditTable[];
}

function originRow(origin: OriginMatchRecord): LineageOriginRow {
  return {
    documentId: origin.document_id,
    organisation: origin.organisation,
    publishedAt: origin.published_at,
    quote: origin.span,
    words: origin.words,
    precedes: origin.precedes,
    isCitation: origin.is_citation,
    countsAsOrigin: origin.eligibility === "ask_first" && !origin.is_citation,
    kind: origin.kind,
  };
}

function adoptionRow(adoption: AmendmentAdoptionRecord): LineageAmendmentRow {
  return {
    amendmentId: adoption.amendment_id,
    stage: adoption.stage,
    committee: adoption.committee,
    authors: authorLabels(adoption),
    tabledOn: adoption.tabled_on,
    adoptedWords: adoption.adopted_words,
    newWords: adoption.new_words,
  };
}

/**
 * Names when the dump gave them, otherwise IDs. Groups pair with author IDs, so they are
 * attached only when names and IDs line up one to one.
 */
function authorLabels(adoption: AmendmentAdoptionRecord): readonly string[] {
  const names = adoption.author_names.length > 0 ? adoption.author_names : adoption.author_ids;
  if (names.length !== adoption.author_ids.length) {
    return names;
  }
  return names.map((name, index) => {
    const group = adoption.author_groups[index];
    return group === undefined || group === null ? name : `${name} (${group})`;
  });
}

function tabledRow(amendmentId: string): LineageAmendmentRow {
  return {
    amendmentId,
    stage: null,
    committee: null,
    authors: [],
    tabledOn: null,
    adoptedWords: null,
    newWords: null,
  };
}

/**
 * Strongest evidence first: a phrase an earlier, non-citation submission asked for, then
 * phrases with any submission, then longer runs. The phrase identifier breaks ties, so the
 * order is the same on every render.
 */
function byEvidence(left: LineagePhraseRow, right: LineagePhraseRow): number {
  return (
    Number(right.hasEarlierRequest) - Number(left.hasEarlierRequest) ||
    Number(right.origins.length > 0) - Number(left.origins.length > 0) ||
    right.words - left.words ||
    left.phraseId.localeCompare(right.phraseId)
  );
}

function hasEarlierRequest(origins: readonly LineageOriginRow[]): boolean {
  return origins.some((origin) => origin.countsAsOrigin);
}

function creditRow(credit: CreditRecord): LineageCreditRow {
  return {
    holderId: credit.holder_id,
    kind: credit.holder_kind,
    name: credit.name,
    phrases: credit.phrases,
    jointPhrases: credit.joint_phrases,
    amendments: credit.amendments,
    amendmentsTabled: credit.amendments_tabled,
  };
}

/**
 * Joins one lineage view into display rows. Throws when a record names a phrase or an
 * amendment the view does not hold: the explorer shows a whole, consistent view or none.
 * Linear in the records of the view, plus sorting the phrases.
 */
export function prepareLineage(view: LineageView): PreparedLineage {
  if (view.schema_version !== "lineage-1") {
    throw new Error(`Unsupported lineage view schema: ${String(view.schema_version)}`);
  }
  const adoptedIds = new Set(view.adopted_phrases.map((phrase) => phrase.phrase_id));
  const tabledIds = new Set(view.tabled_phrases.map((phrase) => phrase.phrase_id));
  const carriers = new Map<string, LineageAmendmentRow[]>();
  const carrierIds = new Map<string, Set<string>>();
  function carry(phraseId: string, row: LineageAmendmentRow) {
    const rows = carriers.get(phraseId) ?? [];
    rows.push(row);
    carriers.set(phraseId, rows);
    const ids = carrierIds.get(phraseId) ?? new Set<string>();
    ids.add(row.amendmentId);
    carrierIds.set(phraseId, ids);
  }
  for (const adoption of view.adoptions) {
    for (const phraseId of adoption.phrase_ids) {
      if (!adoptedIds.has(phraseId)) {
        throw new Error(`${adoption.amendment_id} names ${phraseId}, which the view does not list`);
      }
      carry(phraseId, adoptionRow(adoption));
    }
  }
  for (const phrase of view.tabled_phrases) {
    for (const amendmentId of phrase.amendment_ids) {
      carry(phrase.phrase_id, tabledRow(amendmentId));
    }
  }
  const origins = new Map<string, LineageOriginRow[]>();
  for (const origin of view.origins) {
    if (!adoptedIds.has(origin.phrase_id) && !tabledIds.has(origin.phrase_id)) {
      throw new Error(
        `${origin.document_id} names ${origin.phrase_id}, which the view does not list`,
      );
    }
    const carrying = carrierIds.get(origin.phrase_id) ?? new Set<string>();
    const stranger = origin.amendment_ids.find((id) => !carrying.has(id));
    if (stranger !== undefined) {
      throw new Error(`${origin.document_id} names ${stranger}, which does not carry its phrase`);
    }
    const rows = origins.get(origin.phrase_id) ?? [];
    rows.push(originRow(origin));
    origins.set(origin.phrase_id, rows);
  }

  const adopted = view.adopted_phrases.map((phrase): LineagePhraseRow => {
    const said = origins.get(phrase.phrase_id) ?? [];
    return {
      phraseId: phrase.phrase_id,
      adopted: true,
      kind: phrase.kind,
      text: phrase.text,
      words: phrase.words,
      finalQuotes: phrase.final_spans,
      amendments: carriers.get(phrase.phrase_id) ?? [],
      origins: said,
      hasEarlierRequest: hasEarlierRequest(said),
      joint: phrase.holders.length > 1,
    };
  });
  const tabled = view.tabled_phrases.map((phrase): LineagePhraseRow => {
    const said = origins.get(phrase.phrase_id) ?? [];
    return {
      phraseId: phrase.phrase_id,
      adopted: false,
      kind: "verbatim",
      text: phrase.text,
      words: phrase.words,
      finalQuotes: [],
      amendments: carriers.get(phrase.phrase_id) ?? [],
      origins: said,
      hasEarlierRequest: hasEarlierRequest(said),
      joint: false,
    };
  });

  // The backend orders credits (`credit_rank`); the explorer keeps that order.
  const bases: LineageMatchKind[] = ["verbatim", "semantic"];
  const credits = bases.flatMap((basis): LineageCreditTable[] => {
    const rows = view.credits.filter((credit) => credit.basis === basis).map(creditRow);
    return rows.length === 0
      ? []
      : [
          {
            basis,
            groups: rows.filter((row) => row.kind === "group"),
            holders: rows.filter((row) => row.kind !== "group"),
          },
        ];
  });
  return {
    adopted: [...adopted].sort(byEvidence),
    tabled: [...tabled].sort(byEvidence),
    credits,
  };
}
