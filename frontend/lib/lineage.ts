import type {
  AdoptionEvidenceRecord,
  AmendmentAdoptionRecord,
  CreditRecord,
  LineageEligibility,
  LineageHolderKind,
  LineageMatchKind,
  LineageView,
  OriginMatchRecord,
  OriginSupportRecord,
} from "./lineage-api";
import { indexLineageSources, type LineageSourceIndex } from "./lineage-sources";
import type { SourceSpan } from "./source-span";

/** An amendment that carries a phrase; adoption details exist only for adopted wording. */
export interface LineageAmendmentRow {
  amendmentId: string;
  stage: "committee" | "plenary" | null;
  committee: string | null;
  /** Each author's name, with the political group in brackets when it is known. */
  authors: readonly string[];
  /** The distinct known political groups of its authors, for filtering by group. */
  groups: readonly string[];
  tabledOn: string | null;
  /** Words of the amendment's new text inside adopted wording, of all its words; `null` for tabled wording. */
  adoptedWords: number | null;
  newWords: number | null;
  evidence: readonly AdoptionEvidenceRecord[];
}

/** A submission that says the phrase, with the exact quotation and its date order. */
export interface LineageOriginRow {
  documentId: string;
  /** Saved carrier IDs retained for stable legacy quotation identity. */
  amendmentIds: readonly string[];
  /** `null` for a citizen or an unnamed attachment: the explorer never invents a name. */
  organisation: string | null;
  publishedAt: string | null;
  eligibility: LineageEligibility;
  earliestAmendmentOn: string | null;
  similarity: number | null;
  quote: SourceSpan;
  words: number;
  precedes: boolean | null;
  isCitation: boolean;
  /** Dated before every carrying amendment and not a citation: the backend's `counts_as_origin`. */
  countsAsOrigin: boolean;
  kind: LineageMatchKind;
  supports: readonly OriginSupportRecord[];
}

/** One phrase with every record that cites it, ready to show side by side. */
export interface LineagePhraseRow {
  phraseId: string;
  adopted: boolean;
  kind: LineageMatchKind;
  /** Folded words; the quotations keep the original casing and punctuation. */
  text: string;
  words: number;
  finalQuotes: readonly SourceSpan[];
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
  supportedClaims: SupportedLineageClaims;
  sources: LineageSourceIndex;
}

function originRow(origin: OriginMatchRecord): LineageOriginRow {
  return {
    documentId: origin.document_id,
    amendmentIds: origin.amendment_ids,
    organisation: origin.organisation,
    publishedAt: origin.published_at,
    eligibility: origin.eligibility,
    earliestAmendmentOn: origin.earliest_amendment_on,
    similarity: origin.similarity,
    quote: origin.span,
    words: origin.words,
    precedes: origin.precedes,
    isCitation: origin.is_citation,
    countsAsOrigin: origin.eligibility === "ask_first" && !origin.is_citation,
    kind: origin.kind,
    supports: origin.supports ?? [],
  };
}

function adoptionRow(adoption: AmendmentAdoptionRecord, phraseId: string): LineageAmendmentRow {
  return {
    amendmentId: adoption.amendment_id,
    stage: adoption.stage,
    committee: adoption.committee,
    authors: authorLabels(adoption),
    groups: [...new Set(adoption.author_groups.filter((group) => group !== null))],
    tabledOn: adoption.tabled_on,
    adoptedWords: adoption.adopted_words,
    newWords: adoption.new_words,
    evidence: (adoption.evidence ?? []).filter((evidence) => evidence.phrase_id === phraseId),
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
    groups: [],
    tabledOn: null,
    adoptedWords: null,
    newWords: null,
    evidence: [],
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
  if (view.schema_version !== "lineage-1" && view.schema_version !== "lineage-2") {
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
      carry(phraseId, adoptionRow(adoption, phraseId));
    }
  }
  for (const phrase of view.tabled_phrases) {
    for (const amendmentId of phrase.amendment_ids) {
      carry(phrase.phrase_id, tabledRow(amendmentId));
    }
  }
  const origins = new Map<string, LineageOriginRow[]>();
  const originIdentities = new Map<string, Map<string, LineageOriginRow>>();
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
    const row = originRow(origin);
    // Equal quotations coalesce only when their saved target/presentation metadata agrees.
    // A quotation can precede one carrier but follow another; keep those states separate.
    const presentation = originPresentationKey(row);
    const identities =
      originIdentities.get(origin.phrase_id) ?? new Map<string, LineageOriginRow>();
    const repeated = identities.get(presentation);
    if (repeated === undefined) {
      rows.push(row);
      identities.set(presentation, row);
    } else {
      repeated.amendmentIds = [...new Set([...repeated.amendmentIds, ...row.amendmentIds])].sort();
      repeated.supports = [
        ...new Map(
          [...repeated.supports, ...row.supports].map((support) => [support.support_id, support]),
        ).values(),
      ];
    }
    origins.set(origin.phrase_id, rows);
    originIdentities.set(origin.phrase_id, identities);
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
    supportedClaims: collectSupportedClaims(view),
    sources: indexLineageSources(view),
  };
}

/** One saved carrier-specific association; coauthors share this support identity. */
export interface SupportedLineageClaim {
  claimId: string;
  phraseId: string;
  origin: OriginMatchRecord;
  adoption: AmendmentAdoptionRecord;
  evidence: AdoptionEvidenceRecord;
  support: OriginSupportRecord;
}

export interface SupportedLineageClaims {
  claims: readonly SupportedLineageClaim[];
  /** Legacy and unknown snapshots cannot supply current carrier-specific associations. */
  unavailableReason: string | null;
  /** Eligible adopted origins without current support remain inspectable as saved context. */
  unsupportedOrigins: number;
}

function sameSpan(left: SourceSpan, right: SourceSpan): boolean {
  return (
    left.record_id === right.record_id &&
    left.field === right.field &&
    left.start === right.start &&
    left.end === right.end &&
    left.text === right.text &&
    left.page === right.page
  );
}

function projectsFrom(parent: SourceSpan, child: SourceSpan): boolean {
  return (
    parent.record_id === child.record_id &&
    parent.field === child.field &&
    parent.start <= child.start &&
    child.start < child.end &&
    child.end <= parent.end &&
    [...parent.text].slice(child.start - parent.start, child.end - parent.start).join("") ===
      child.text
  );
}

/**
 * Joins saved support IDs to their own carrier and final occurrence. It never infers a
 * carrier from a merged phrase. Linear in records plus the quoted text checked at joins.
 * The backend validates the matching rules; these checks protect referential identity.
 */
export function collectSupportedClaims(view: LineageView): SupportedLineageClaims {
  if (view.schema_version === "lineage-1") {
    return {
      claims: [],
      unavailableReason:
        "This legacy snapshot lacks carrier-specific evidence. Current graph associations and organisation ranking are unavailable; saved quotations and adoption counts remain inspectable.",
      unsupportedOrigins: 0,
    };
  }
  if (view.status === "unknown") {
    return {
      claims: [],
      unavailableReason: "Adoption is unknown, so carrier-specific associations are unavailable.",
      unsupportedOrigins: 0,
    };
  }
  const phrases = new Map(view.adopted_phrases.map((phrase) => [phrase.phrase_id, phrase]));
  const carriers = new Map<
    string,
    { adoption: AmendmentAdoptionRecord; evidence: AdoptionEvidenceRecord }
  >();
  for (const adoption of view.adoptions) {
    for (const evidence of adoption.evidence ?? []) {
      const phrase = phrases.get(evidence.phrase_id);
      if (carriers.has(evidence.evidence_id)) {
        throw new Error(`Duplicate carrier evidence: ${evidence.evidence_id}`);
      }
      if (
        phrase === undefined ||
        adoption.kind !== "verbatim" ||
        phrase.kind !== "verbatim" ||
        !adoption.phrase_ids.includes(evidence.phrase_id) ||
        evidence.amendment_span.record_id !== adoption.amendment_id ||
        evidence.amendment_span.field !== "new_text" ||
        evidence.final_span.field !== "text" ||
        evidence.inserted_word_offsets.length === 0 ||
        !phrase.final_spans.some((span) => projectsFrom(span, evidence.final_span))
      ) {
        throw new Error(`Invalid carrier evidence: ${evidence.evidence_id}`);
      }
      carriers.set(evidence.evidence_id, { adoption, evidence });
    }
  }
  const claims: SupportedLineageClaim[] = [];
  const supportIds = new Set<string>();
  let unsupportedOrigins = 0;
  for (const origin of view.origins) {
    if (
      !phrases.has(origin.phrase_id) ||
      origin.eligibility !== "ask_first" ||
      origin.is_citation ||
      origin.organisation === null
    ) {
      continue;
    }
    if (origin.kind !== "verbatim" || (origin.supports ?? []).length === 0) {
      unsupportedOrigins += 1;
      continue;
    }
    for (const support of origin.supports ?? []) {
      const carrier = carriers.get(support.adoption_evidence_id);
      if (supportIds.has(support.support_id)) {
        throw new Error(`Duplicate association support: ${support.support_id}`);
      }
      supportIds.add(support.support_id);
      if (
        carrier === undefined ||
        carrier.adoption.amendment_id !== support.amendment_id ||
        carrier.evidence.phrase_id !== origin.phrase_id ||
        !origin.amendment_ids.includes(support.amendment_id) ||
        support.submission_span.record_id !== origin.document_id ||
        !sameSpan(support.submission_span, origin.span) ||
        !projectsFrom(carrier.evidence.amendment_span, support.amendment_span) ||
        !projectsFrom(carrier.evidence.final_span, support.final_span)
      ) {
        throw new Error(`Invalid association support: ${support.support_id}`);
      }
      claims.push({
        claimId: support.support_id,
        phraseId: origin.phrase_id,
        origin,
        adoption: carrier.adoption,
        evidence: carrier.evidence,
        support,
      });
    }
  }
  return {
    claims: claims.sort((left, right) => left.claimId.localeCompare(right.claimId)),
    unavailableReason:
      claims.length === 0 && unsupportedOrigins > 0
        ? "Saved adopted origins lack carrier-specific evidence. Current graph associations and organisation ranking are unavailable; saved quotations and adoption counts remain inspectable."
        : null,
    unsupportedOrigins,
  };
}

/**
 * Exact quotation plus its saved carrier identity, without order-dependent row indices.
 * O(n log n) for sorting one quotation's support/carrier IDs; usually a handful per row.
 */
export function originRowKey(origin: LineageOriginRow): string {
  const carrierIds =
    origin.supports.length > 0
      ? origin.supports.map((support) => support.support_id)
      : origin.amendmentIds;
  return JSON.stringify([originPresentationKey(origin), [...new Set(carrierIds)].sort()]);
}

/** One shared identity tuple for deduplication and render-key discrimination. */
function originPresentationKey(origin: LineageOriginRow): string {
  return JSON.stringify([
    origin.documentId,
    origin.kind,
    origin.quote.field,
    origin.quote.start,
    origin.quote.end,
    origin.quote.page,
    origin.quote.text,
    origin.organisation,
    origin.publishedAt,
    origin.words,
    origin.precedes,
    origin.isCitation,
    origin.countsAsOrigin,
    origin.eligibility,
    origin.earliestAmendmentOn,
    origin.similarity,
  ]);
}
