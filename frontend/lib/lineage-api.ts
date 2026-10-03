import type { AtlasSourceSpan } from "./atlas";
import { type AtlasLayerCoverage, readApiJson } from "./atlas-api";

/**
 * The lineage read API: `GET /api/v1/lineage` lists the laws with a built lineage view, and
 * `GET /api/v1/lineage/{slug}` returns one law's view. These types describe the JSON of
 * `backend/src/influence/schemas/lineage.py`; they are not a runtime decoder. `lib/lineage.ts`
 * checks the references between records.
 */

export type LineageMatchKind = "verbatim" | "semantic";
export type LineageHolderKind = "mep" | "group" | "committee_text" | "organisation";

/** One law with a lineage view, as the law selector shows it. */
export interface LineageLawSummary {
  /** The procedure reference made URL-safe, e.g. `2021-0106-COD`; it names the law in URLs. */
  slug: string;
  procedure_id: string;
  title: string;
  run_id: string;
  adopted_phrases: number;
  amendments_adopting: number;
  documents_with_origin: number;
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
  final_spans: readonly AtlasSourceSpan[];
  similarity: number | null;
  judge_probability: number | null;
}

/** Wording amendments inserted that a submission also says, and that was not adopted. */
export interface TabledPhraseRecord {
  phrase_id: string;
  text: string;
  words: number;
  amendment_ids: readonly string[];
}

/** One amendment whose inserted wording reached the final act. */
export interface AmendmentAdoptionRecord {
  amendment_id: string;
  kind: LineageMatchKind;
  stage: "committee" | "plenary";
  committee: string | null;
  author_ids: readonly string[];
  author_names: readonly string[];
  author_groups: readonly string[];
  tabled_on: string | null;
  phrase_ids: readonly string[];
  adopted_words: number;
  inserted_words: number;
  longest_run: number;
}

/** A submission that says a phrase, dated against the amendments that carry it. */
export interface OriginMatchRecord {
  phrase_id: string;
  document_id: string;
  actor_id: string | null;
  organisation: string | null;
  published_at: string | null;
  span: AtlasSourceSpan;
  kind: LineageMatchKind;
  similarity: number | null;
  words: number;
  amendment_ids: readonly string[];
  earliest_amendment_on: string | null;
  /** `null` when either date is unknown: an undated document is never shown as first. */
  precedes: boolean | null;
  /** A quotation of another act or of the proposal: shared wording, not a request. */
  is_citation: boolean;
}

/** How much adopted wording one holder is credited with; each phrase is worth 1, split. */
export interface CreditRecord {
  holder_id: string;
  basis: LineageMatchKind;
  holder_kind: LineageHolderKind;
  name: string;
  phrases: number;
  distinct_phrases: number;
  amendments: number;
}

export interface LineageCounts {
  amendments: number;
  amendments_adopting: number;
  adopted_phrases: number;
  documents_read: number;
  documents_with_origin: number;
  /** Units of new final-act wording; 0 when the run did not measure it. */
  changed_units: number;
  linked_units: number;
}

/** Everything the explorer shows for one law's lineage, from one run. */
export interface LineageView {
  schema_version: "lineage-1";
  procedure_id: string;
  slug: string;
  title: string;
  run_id: string;
  generated_at: string;
  method: string;
  method_revision: string;
  coverage: readonly AtlasLayerCoverage[];
  counts: LineageCounts;
  adopted_phrases: readonly AdoptedPhraseRecord[];
  tabled_phrases: readonly TabledPhraseRecord[];
  adoptions: readonly AmendmentAdoptionRecord[];
  origins: readonly OriginMatchRecord[];
  /** Ordered from most to least within each basis by the backend; the view keeps that order. */
  credits: readonly CreditRecord[];
  limitations: readonly string[];
}

export const lineageLawsUrl = "/api/v1/lineage";

export function lineageViewUrl(slug: string): string {
  return `${lineageLawsUrl}/${encodeURIComponent(slug)}`;
}

/** Reads `GET /api/v1/lineage`; with `useResource`, the URL keys and cancels the request. */
export function readLineageLaws(url: string, signal: AbortSignal): Promise<LineageLawList> {
  return readApiJson(url, signal);
}

/** Reads `GET /api/v1/lineage/{slug}`; a law without a view answers 404 as an `AtlasApiError`. */
export function readLineageView(url: string, signal: AbortSignal): Promise<LineageView> {
  return readApiJson(url, signal);
}
