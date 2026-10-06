/** The coverage rows part 1 (collect) records for a law: one per source layer. */
export type Layer =
  | "metadata"
  | "proposal"
  | "parliament_position"
  | "final_act"
  | "committee_amendments"
  | "plenary_amendments"
  | "asks"
  | "actors"
  | "meetings"
  | "votes";
/** `missing`: the source lacks it; `not_collected`: the run did not try; `stale`: the source stopped updating. */
export type LayerStatus =
  | "complete"
  | "partial"
  | "missing"
  | "stale"
  | "not_applicable"
  | "not_collected";
/** How completely one source layer was collected for the law. */
export interface LayerCoverage {
  layer: Layer;
  status: LayerStatus;
  /** `null` means not counted, which differs from a counted zero. */
  count: number | null;
  /** Always present when the status is not `complete`. */
  reason: string | null;
  source_updated_on: string | null;
}
