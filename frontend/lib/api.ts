/** The versioned read-only demo API. Offsets count Unicode code points, not UTF-16 units. */
export interface TextSpan {
  start: number;
  end: number;
  text: string;
}
export interface ChangeSpan extends TextSpan {
  operation: "insert" | "delete";
}
export interface ScoreResult {
  score: number;
  score_type: "lexical_similarity";
  method: "lexical-delta-v1";
  amendment_changes: ChangeSpan[];
  submission_changes: ChangeSpan[];
  evidence: { operation: "insert" | "delete"; amendment: TextSpan; submission: TextSpan }[];
  negation_conflict: boolean;
  limitations: string[];
}
export interface AmendmentSummary {
  id: string;
  committee: string;
  number: number;
  authors: string[];
  relations: string[];
  verified_links: number;
  candidate_links: number;
}
export interface AmendmentPage {
  items: AmendmentSummary[];
  total: number;
  offset: number;
  limit: number;
}
export interface SourceText {
  language: string;
  old: string;
  new: string;
}
export interface SourceMatch {
  candidate_id: string;
  proposal_id: string;
  organization_id: string;
  organization: string;
  document_id: string;
  document: string;
  page: string;
  text: SourceText;
  historically_verified: boolean;
  score: ScoreResult | null;
  score_unavailable_reason: string | null;
}
export interface AmendmentDetail {
  amendment: AmendmentSummary;
  text: SourceText;
  sources: SourceMatch[];
  total_sources: number;
  coverage_note: string;
}
export interface DatasetOverview {
  amendments: number;
  proposals: number;
  documents: number;
  organizations: number;
  candidate_links: number;
  duplicate_candidate_rows: number;
  verified_links: number;
  source_url: string;
  coverage_note: string;
}
export interface GraphNode {
  id: string;
  kind: "amendment" | "organization" | "author";
  label: string;
}
export interface InfluenceGraph {
  amendment_id: string;
  nodes: GraphNode[];
  edges: { source: string; target: string; kind: "historically_verified" | "authored" }[];
  coverage_note: string;
}

/** Missing originals are explicit; the server selects passage or edit comparison. */
export interface ComparisonResult {
  mode: "edits" | "passages";
  method: "lexical-delta-v1" | "lexical-passage-v1";
  score: number;
  evidence: ScoreResult["evidence"];
  negation_conflict: boolean;
  limitations: string[];
}
