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
  authors: readonly string[];
  tabledOn: string | null;
  /** Words of this amendment that stand in the final act; `null` for tabled wording. */
  adoptedWords: number | null;
  insertedWords: number | null;
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
  /** At least one submission said it before the amendments and is not a citation. */
  hasEarlierRequest: boolean;
}

export interface LineageCreditRow {
  holderId: string;
  kind: LineageHolderKind;
  name: string;
  phrases: number;
  distinctPhrases: number;
  amendments: number;
}

export interface LineageCreditTable {
  basis: LineageMatchKind;
  groups: readonly LineageCreditRow[];
  /** MEPs and the committee's own text, which has no individual author. */
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
    kind: origin.kind,
  };
}

function adoptionRow(adoption: AmendmentAdoptionRecord): LineageAmendmentRow {
  return {
    amendmentId: adoption.amendment_id,
    stage: adoption.stage,
    committee: adoption.committee,
    authors: adoption.author_names.length > 0 ? adoption.author_names : adoption.author_ids,
    tabledOn: adoption.tabled_on,
    adoptedWords: adoption.adopted_words,
    insertedWords: adoption.inserted_words,
  };
}

function tabledRow(amendmentId: string): LineageAmendmentRow {
  return {
    amendmentId,
    stage: null,
    committee: null,
    authors: [],
    tabledOn: null,
    adoptedWords: null,
    insertedWords: null,
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
  return origins.some((origin) => origin.precedes === true && !origin.isCitation);
}

function creditRow(credit: CreditRecord): LineageCreditRow {
  return {
    holderId: credit.holder_id,
    kind: credit.holder_kind,
    name: credit.name,
    phrases: credit.phrases,
    distinctPhrases: credit.distinct_phrases,
    amendments: credit.amendments,
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
    };
  });

  // The backend orders credits within each basis; the explorer keeps that order.
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
