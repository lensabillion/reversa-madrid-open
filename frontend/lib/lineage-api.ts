import { readJson } from "./api-client";
import type { LayerCoverage } from "./coverage";
import type { SourceSpan } from "./source-span";

/**
 * The lineage read API: `GET /api/v1/lineage` lists the laws with a built lineage view, and
 * `GET /api/v1/lineage/{slug}` returns one law's view. These types describe the JSON of
 * `backend/src/influence/schemas/lineage.py`; they are not a runtime decoder. `lib/lineage.ts`
 * checks the references between records.
 */

export type LineageMatchKind = "verbatim" | "semantic";
export type LineageHolderKind = "mep" | "group" | "unresolved" | "committee_text" | "organisation";
export type LineageStatus = "computed" | "unknown";
/** Did the document (the ask) come before every amendment carrying the phrase? */
export type LineageEligibility = "ask_first" | "amendment_first" | "unknown_date";

/** One law with a lineage view, as the law selector shows it. */
export interface LineageLawSummary {
  /** The procedure reference made URL-safe, e.g. `2021-0106-COD`; it names the law in URLs. */
  slug: string;
  procedure_id: string;
  title: string;
  run_id: string;
  status: LineageStatus;
  /** `null` when the view could not compute it, never a stand-in zero. */
  adopted_phrases: number | null;
  amendments_adopting: number | null;
  documents_with_origin: number | null;
}
export interface LineageLawList {
  laws: LineageLawSummary[];
}

/** Wording that stands in the final act, is not in the proposal, and an amendment inserted. */
export interface AdoptedPhraseRecord {
  phrase_id: string;
  kind: LineageMatchKind;
  /** Folded words (lower case, alphanumeric) joined by spaces; `final_spans` quote the original. */
  text: string;
  words: number;
  final_spans: readonly SourceSpan[];
  similarity: number | null;
  judge_probability: number | null;
  /** Credit keys of everyone credited with it; the phrase is joint when there are several. */
  holders: readonly string[];
}

/** Wording amendments inserted that a submission also says, and that was not adopted. */
export interface TabledPhraseRecord {
  phrase_id: string;
  text: string;
  words: number;
  amendment_ids: readonly string[];
}

/** One exact accepted amendment run and its paired final-act occurrence. */
export interface AdoptionEvidenceRecord {
  evidence_id: string;
  phrase_id: string;
  amendment_span: SourceSpan;
  final_span: SourceSpan;
  inserted_word_offsets: readonly number[];
}

/** Exact three-source projection of one accepted amendment carrier. */
export interface OriginSupportRecord {
  support_id: string;
  adoption_evidence_id: string;
  amendment_id: string;
  submission_span: SourceSpan;
  amendment_span: SourceSpan;
  final_span: SourceSpan;
}

/** One amendment whose inserted wording reached the final act. */
export interface AmendmentAdoptionRecord {
  amendment_id: string;
  kind: LineageMatchKind;
  stage: "committee" | "plenary";
  committee: string | null;
  author_ids: readonly string[];
  author_names: readonly string[];
  /** One per author ID, `null` where the group is unknown; empty without author IDs. */
  author_groups: readonly (string | null)[];
  tabled_on: string | null;
  phrase_ids: readonly string[];
  adopted_words: number;
  inserted_words: number;
  new_words: number;
  longest_run: number;
  /** Absent on legacy snapshots; never reconstructed by the browser. */
  evidence?: readonly AdoptionEvidenceRecord[];
}

/** A submission that says a phrase, dated against the amendments that carry it. */
export interface OriginMatchRecord {
  phrase_id: string;
  document_id: string;
  actor_id: string | null;
  organisation: string | null;
  published_at: string | null;
  span: SourceSpan;
  kind: LineageMatchKind;
  similarity: number | null;
  words: number;
  amendment_ids: readonly string[];
  earliest_amendment_on: string | null;
  /** `null` when a date is unknown: an undated document is never shown as first. */
  precedes: boolean | null;
  eligibility: LineageEligibility;
  /** A quotation of another act or of the proposal: shared wording, not a request. */
  is_citation: boolean;
  /** Absent on legacy or unsupported records; never inferred from phrase IDs. */
  supports?: readonly OriginSupportRecord[];
}

/**
 * The adopted wording one holder is credited with: every holder of a phrase gets the whole
 * phrase (no fractional credit), and the rate is `amendments` adopted of `amendments_tabled`.
 */
export interface CreditRecord {
  holder_id: string;
  basis: LineageMatchKind;
  holder_kind: LineageHolderKind;
  name: string;
  phrases: number;
  joint_phrases: number;
  amendments: number;
  amendments_tabled: number;
}

/** A count is `null` until it has been computed, never zero. */
export interface LineageCounts {
  amendments: number;
  amendments_adopting: number | null;
  adopted_phrases: number | null;
  phrases_without_group: number | null;
  documents_read: number | null;
  documents_with_origin: number | null;
  /** Words of the final act in a window the proposal lacks, and those inside adopted phrases. */
  changed_units: number | null;
  linked_units: number | null;
}

/** Everything the explorer shows for one law's lineage, from one run. */
export interface LineageView {
  schema_version: "lineage-1" | "lineage-2";
  procedure_id: string;
  slug: string;
  title: string;
  run_id: string;
  generated_at: string;
  method: string;
  method_revision: string;
  coverage: readonly LayerCoverage[];
  /** `unknown` when the proposal or the final act is missing; `reason` then says which. */
  status: LineageStatus;
  reason: string | null;
  counts: LineageCounts;
  adopted_phrases: readonly AdoptedPhraseRecord[];
  tabled_phrases: readonly TabledPhraseRecord[];
  adoptions: readonly AmendmentAdoptionRecord[];
  origins: readonly OriginMatchRecord[];
  /** In the backend's `credit_rank` order (basis, kind, then rate); the view keeps that order. */
  credits: readonly CreditRecord[];
  limitations: readonly string[];
}

export const lineageLawsUrl = "/api/v1/lineage";

export function lineageViewUrl(slug: string): string {
  return `${lineageLawsUrl}/${encodeURIComponent(slug)}`;
}

/** Reads `GET /api/v1/lineage`; with `useResource`, the URL keys and cancels the request. */
export function readLineageLaws(url: string, signal: AbortSignal): Promise<LineageLawList> {
  return readJson(url, signal);
}

/** Reads `GET /api/v1/lineage/{slug}`; a law without a view answers 404 as an `ApiError`. */
export function readLineageView(url: string, signal: AbortSignal): Promise<LineageView> {
  return readJson(url, signal);
}
