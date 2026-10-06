import type { AtlasBundle, AtlasSourceSpan } from "./atlas";

/**
 * The Atlas read API: `GET /api/v1/atlas` lists the laws with a built Atlas run, and
 * `GET /api/v1/atlas/{slug}` returns one law's view. These types describe
 * the backend's JSON; they are not a runtime decoder. `lib/atlas.ts` checks the bundle.
 */

/** One law with a built Atlas run, as the law selector shows it. */
export interface AtlasLawSummary {
  /** The procedure reference made URL-safe, e.g. `2021-0106-COD`; it names the law in URLs. */
  slug: string;
  /** The Legislative Observatory reference, e.g. `2021/0106(COD)`. */
  procedure_id: string;
  title: string;
  run_id: string;
  published_links: number;
}
export interface AtlasLawList {
  laws: AtlasLawSummary[];
}

export type AtlasLayer =
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
export type AtlasLayerStatus =
  | "complete"
  | "partial"
  | "missing"
  | "stale"
  | "not_applicable"
  | "not_collected";
/** How completely one source layer was collected for the law. */
export interface AtlasLayerCoverage {
  layer: AtlasLayer;
  status: AtlasLayerStatus;
  /** `null` means not counted, which differs from a counted zero. */
  count: number | null;
  /** Always present when the status is not `complete`. */
  reason: string | null;
  source_updated_on: string | null;
}

interface AtlasGraphNodeRecord {
  node_id: string;
  kind: "actor" | "ask" | "amendment" | "article" | "procedure" | "topic";
  label: string;
  record_id: string;
}
interface AtlasGraphEdgeRecord {
  edge_id: string;
  relation:
    | "REQUESTED"
    | "ECHOED_BY"
    | "TABLED_BY"
    | "EDITS"
    | "ALIGNED_TO"
    | "REALIZED_IN"
    | "MET_WITH"
    | "MEMBER_OF"
    | "ABOUT";
  source: string;
  target: string;
  spans: readonly AtlasSourceSpan[];
  link_id: string | null;
  outcome_id: string | null;
  dated_on: string | null;
}
/** The backend's `GraphSnapshot`: the graph built from published links only. */
export interface AtlasSnapshotRecord {
  schema_version: "atlas-1";
  snapshot_id: string;
  run_id: string;
  generated_at: string;
  procedure_ids: readonly string[];
  nodes: readonly AtlasGraphNodeRecord[];
  edges: readonly AtlasGraphEdgeRecord[];
  coverage: Record<string, readonly AtlasLayerCoverage[]>;
}

/** One actor's final-act outcome counts; the backend orders the rows and the view keeps that order. */
export interface AtlasRanking {
  actor_id: string;
  actor_name: string;
  /** Every observed ask, including unknown outcomes. */
  observed_asks: number;
  /** Asks with a known outcome (full, partial or not observed); excludes unknown. */
  assessed_asks: number;
  full: number;
  partial: number;
  not_observed: number;
  unknown: number;
  full_win_rate: number | null;
  evidence_record_ids: readonly string[];
}

/** Everything the explorer shows for one law, from one Atlas run. */
export interface AtlasView {
  schema_version: "atlas-view-1";
  procedure_id: string;
  slug: string;
  title: string;
  run_id: string;
  generated_at: string;
  /** The ask extraction method; its limits are among `limitations`. */
  ask_method: string;
  coverage: readonly AtlasLayerCoverage[];
  /** Links whose status is published, unconfirmed or contradicted, and the records they cite. */
  bundle: AtlasBundle;
  /**
   * Labels for what this run could not show, e.g. "Negotiation in progress". Files written
   * before the field existed lack it; read it through `atlasModes`.
   */
  modes?: readonly string[];
  snapshot: AtlasSnapshotRecord;
  rankings: readonly AtlasRanking[];
  limitations: readonly string[];
}

/** A non-2xx answer from the Atlas API, carrying the backend's own explanation. */
export class AtlasApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`The Atlas API answered ${status}: ${detail}`);
    this.name = "AtlasApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** The view's mode labels; an older file without the field has none. */
export function atlasModes(view: AtlasView): readonly string[] {
  return view.modes ?? [];
}

export const atlasLawsUrl = "/api/v1/atlas";

export function atlasViewUrl(slug: string): string {
  return `${atlasLawsUrl}/${encodeURIComponent(slug)}`;
}

/** FastAPI sends `detail` as a string, or as a list of validation issues for a 422. */
async function errorDetail(response: Response): Promise<string> {
  if (response.headers.get("Content-Type")?.includes("application/json")) {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      if (typeof body.detail === "string") {
        return body.detail;
      }
      if (Array.isArray(body.detail)) {
        const messages = body.detail.flatMap((issue: unknown) =>
          typeof issue === "object" &&
          issue !== null &&
          "msg" in issue &&
          typeof issue.msg === "string"
            ? [issue.msg]
            : [],
        );
        if (messages.length > 0) {
          return messages.join("; ");
        }
      }
    }
  }
  return response.statusText || "no detail was supplied";
}

/** Reads one answer of the backend read API (Atlas or lineage); the caller owns the check of `T`. */
export async function readAtlasJson<T>(url: string, signal: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { signal, cache: "no-store" });
  } catch (error: unknown) {
    if (signal.aborted) {
      throw error;
    }
    throw new Error(`The API could not be reached at ${url}.`, { cause: error });
  }
  if (!response.ok) {
    throw new AtlasApiError(response.status, await errorDetail(response));
  }
  const data: T = await response.json();
  return data;
}

/** Reads `GET /api/v1/atlas`; with `useResource`, the URL keys and cancels the request. */
export function readAtlasLaws(url: string, signal: AbortSignal): Promise<AtlasLawList> {
  return readAtlasJson(url, signal);
}

/** Reads `GET /api/v1/atlas/{slug}`; a law without a run answers 404 as an `AtlasApiError`. */
export function readAtlasView(url: string, signal: AbortSignal): Promise<AtlasView> {
  return readAtlasJson(url, signal);
}
