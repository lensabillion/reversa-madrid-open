import type { AtlasSourceSpan } from "./atlas";
import { AtlasApiError, atlasViewUrl, readAtlasJson } from "./atlas-api";

/**
 * `GET /api/v1/atlas/{slug}/coordinated`: clusters of tabled amendments whose inserted wording
 * is near-identical. The Python source of truth is `backend/src/influence/schemas/coordinated.py`.
 * A cluster is a candidate for a shared draft, never proof of one, and the explorer renders the
 * clusters in the order the API sends them: it holds no scoring or ranking logic.
 */

/** One amendment of a cluster, with the wording it inserts quoted from its `new_text`. */
export interface AtlasClusterMember {
  amendment_id: string;
  stage: string;
  committee: string | null;
  tabled_on: string | null;
  target_provision: string | null;
  author_ids: readonly string[];
  author_names: readonly string[];
  /** Empty means the groups are unknown, not that the authors sit in no group. */
  political_groups: readonly string[];
  inserted: readonly AtlasSourceSpan[];
}
export interface AtlasCoordinatedCluster {
  cluster_id: string;
  members: readonly AtlasClusterMember[];
  political_groups: readonly string[];
  cross_group: boolean;
  /** Inserted words of the member that inserts the fewest. */
  inserted_words: number;
  /** The least similar pair: a cluster joins amendments through chains of similar pairs. */
  min_similarity: number;
}
/** Every amendment of the law is in exactly one of the last three counts. */
export interface AtlasCoordinationCounts {
  amendments: number;
  compared: number;
  too_short: number;
  not_comparable: number;
}
export interface AtlasCoordinatedView {
  schema_version: "atlas-1";
  procedure_id: string;
  slug: string;
  title: string;
  run_id: string;
  generated_at: string;
  method: string;
  min_inserted_words: number;
  shingle_words: number;
  similarity_threshold: number;
  counts: AtlasCoordinationCounts;
  clusters: readonly AtlasCoordinatedCluster[];
  limitations: readonly string[];
}

/** A law without a cluster file is an expected answer here, not a failure to load. */
export type AtlasCoordinatedResult =
  | { found: true; view: AtlasCoordinatedView }
  | { found: false; detail: string };

export function atlasCoordinatedUrl(slug: string): string {
  return `${atlasViewUrl(slug)}/coordinated`;
}

function invalid(path: string, expected: string): never {
  throw new Error(`Invalid coordinated amendments data: ${path} must be ${expected}.`);
}

function record(value: unknown, path: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return invalid(path, "an object");
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, path: string): string {
  return typeof value === "string" && value !== "" ? value : invalid(path, "a non-empty string");
}

function textOrNull(value: unknown, path: string): string | null {
  return value === null || typeof value === "string" ? value : invalid(path, "a string or null");
}

function count(value: unknown, path: string): number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0
    ? value
    : invalid(path, "a non-negative integer");
}

function share(value: unknown, path: string): number {
  return typeof value === "number" && value >= 0 && value <= 1
    ? value
    : invalid(path, "a number from 0 to 1");
}

function list<T>(
  value: unknown,
  path: string,
  minimum: number,
  item: (value: unknown, path: string) => T,
): T[] {
  if (!Array.isArray(value) || value.length < minimum) {
    return invalid(path, minimum === 0 ? "a list" : `a list of at least ${minimum}`);
  }
  return value.map((entry: unknown, index) => item(entry, `${path}[${index}]`));
}

function plainText(value: unknown, path: string): string {
  return typeof value === "string" ? value : invalid(path, "a string");
}

const spanFields = ["text", "old_text", "new_text", "justification"] as const;

function span(value: unknown, path: string): AtlasSourceSpan {
  const row = record(value, path);
  const field = spanFields.find((name) => name === row.field);
  if (field === undefined) {
    return invalid(`${path}.field`, "a source field");
  }
  if (row.page !== null && typeof row.page !== "number") {
    return invalid(`${path}.page`, "a number or null");
  }
  return {
    record_id: text(row.record_id, `${path}.record_id`),
    field,
    start: count(row.start, `${path}.start`),
    end: count(row.end, `${path}.end`),
    text: text(row.text, `${path}.text`),
    page: row.page,
  };
}

function member(value: unknown, path: string): AtlasClusterMember {
  const row = record(value, path);
  return {
    amendment_id: text(row.amendment_id, `${path}.amendment_id`),
    stage: text(row.stage, `${path}.stage`),
    committee: textOrNull(row.committee, `${path}.committee`),
    tabled_on: textOrNull(row.tabled_on, `${path}.tabled_on`),
    target_provision: textOrNull(row.target_provision, `${path}.target_provision`),
    author_ids: list(row.author_ids, `${path}.author_ids`, 0, plainText),
    author_names: list(row.author_names, `${path}.author_names`, 0, plainText),
    political_groups: list(row.political_groups, `${path}.political_groups`, 0, plainText),
    inserted: list(row.inserted, `${path}.inserted`, 1, span),
  };
}

function cluster(value: unknown, path: string): AtlasCoordinatedCluster {
  const row = record(value, path);
  if (typeof row.cross_group !== "boolean") {
    return invalid(`${path}.cross_group`, "true or false");
  }
  return {
    cluster_id: text(row.cluster_id, `${path}.cluster_id`),
    members: list(row.members, `${path}.members`, 2, member),
    political_groups: list(row.political_groups, `${path}.political_groups`, 0, plainText),
    cross_group: row.cross_group,
    inserted_words: count(row.inserted_words, `${path}.inserted_words`),
    min_similarity: share(row.min_similarity, `${path}.min_similarity`),
  };
}

/**
 * Checks the response against the backend's `CoordinatedView` and throws on the first field
 * that breaks it, so the panel shows an error instead of a partial or repaired cluster list.
 * O(size of the response); the AI Act's file holds 269 clusters in about 0.6 MB.
 */
export function coordinatedView(value: unknown): AtlasCoordinatedView {
  const row = record(value, "the response");
  if (row.schema_version !== "atlas-1") {
    throw new Error(`Unsupported coordinated amendments schema: ${String(row.schema_version)}`);
  }
  const counts = record(row.counts, "counts");
  return {
    schema_version: "atlas-1",
    procedure_id: text(row.procedure_id, "procedure_id"),
    slug: text(row.slug, "slug"),
    title: text(row.title, "title"),
    run_id: text(row.run_id, "run_id"),
    generated_at: text(row.generated_at, "generated_at"),
    method: text(row.method, "method"),
    min_inserted_words: count(row.min_inserted_words, "min_inserted_words"),
    shingle_words: count(row.shingle_words, "shingle_words"),
    similarity_threshold: share(row.similarity_threshold, "similarity_threshold"),
    counts: {
      amendments: count(counts.amendments, "counts.amendments"),
      compared: count(counts.compared, "counts.compared"),
      too_short: count(counts.too_short, "counts.too_short"),
      not_comparable: count(counts.not_comparable, "counts.not_comparable"),
    },
    clusters: list(row.clusters, "clusters", 0, cluster),
    limitations: list(row.limitations, "limitations", 0, plainText),
  };
}

/** Reads the law's clusters; a 404 (no cluster file) is a result, every other failure throws. */
export async function readAtlasCoordinated(
  url: string,
  signal: AbortSignal,
): Promise<AtlasCoordinatedResult> {
  try {
    return { found: true, view: coordinatedView(await readAtlasJson<unknown>(url, signal)) };
  } catch (error: unknown) {
    if (error instanceof AtlasApiError && error.status === 404) {
      return { found: false, detail: error.detail };
    }
    throw error;
  }
}
