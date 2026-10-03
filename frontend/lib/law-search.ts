import { errorDetail } from "./atlas-api";

/**
 * The law search and build API: `GET /api/v1/laws/search?q=` resolves any EU law reference,
 * `POST /api/v1/laws/{slug}/build` starts the pipeline for it, and `GET` on the same path
 * reports its progress. Every answer is checked at runtime: a contract break is an error,
 * never a repaired value.
 */

export type BuildPhase = "queued" | "running" | "done" | "failed";
export type BuildStep = "lineage" | "atlas";

export interface BuildState {
  slug: string;
  procedure_id: string;
  state: BuildPhase;
  step: string | null;
  steps: string[];
  started_at: string;
  finished_at: string | null;
  error: string | null;
  log: string[];
}

export interface LawHit {
  procedure_id: string;
  title: string;
  slug: string;
  has_lineage: boolean;
  has_atlas: boolean;
  build: BuildState | null;
}

export interface LawSearch {
  query: string;
  status: "found" | "ambiguous" | "not_found";
  law: LawHit | null;
  choices: LawHit[];
  message: string | null;
}

/** A typed answer: the value, or the backend's `detail` with its status (`null`: unreachable). */
export type LawApiResult<T> =
  | { ok: true; value: T }
  | { ok: false; status: number | null; detail: string };

type Fields = Record<string, unknown>;

function fields(value: unknown, what: string): Fields {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${what} is not an object.`);
  }
  return value as Fields;
}

function text(record: Fields, key: string, what: string): string {
  const value = record[key];
  if (typeof value !== "string") {
    throw new Error(`${what}.${key} is not a string.`);
  }
  return value;
}

function optionalText(record: Fields, key: string, what: string): string | null {
  return record[key] === null ? null : text(record, key, what);
}

function flag(record: Fields, key: string, what: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") {
    throw new Error(`${what}.${key} is not a boolean.`);
  }
  return value;
}

function texts(record: Fields, key: string, what: string): string[] {
  const value = record[key];
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new Error(`${what}.${key} is not a list of strings.`);
  }
  return value;
}

const phases: readonly BuildPhase[] = ["queued", "running", "done", "failed"];

export function parseBuildState(value: unknown): BuildState {
  const what = "BuildState";
  const record = fields(value, what);
  const phase = phases.find((candidate) => candidate === record.state);
  if (phase === undefined) {
    throw new Error(`${what}.state is not one of ${phases.join(", ")}.`);
  }
  return {
    slug: text(record, "slug", what),
    procedure_id: text(record, "procedure_id", what),
    state: phase,
    step: optionalText(record, "step", what),
    steps: texts(record, "steps", what),
    started_at: text(record, "started_at", what),
    finished_at: optionalText(record, "finished_at", what),
    error: optionalText(record, "error", what),
    log: texts(record, "log", what),
  };
}

function parseLawHit(value: unknown): LawHit {
  const what = "LawHit";
  const record = fields(value, what);
  return {
    procedure_id: text(record, "procedure_id", what),
    title: text(record, "title", what),
    slug: text(record, "slug", what),
    has_lineage: flag(record, "has_lineage", what),
    has_atlas: flag(record, "has_atlas", what),
    build: record.build === null ? null : parseBuildState(record.build),
  };
}

export function parseLawSearch(value: unknown): LawSearch {
  const what = "LawSearch";
  const record = fields(value, what);
  const status = record.status;
  if (status !== "found" && status !== "ambiguous" && status !== "not_found") {
    throw new Error(`${what}.status is not found, ambiguous or not_found.`);
  }
  const choices = record.choices;
  if (!Array.isArray(choices)) {
    throw new Error(`${what}.choices is not a list.`);
  }
  const law = record.law === null ? null : parseLawHit(record.law);
  if (status === "found" && law === null) {
    throw new Error(`${what}.law is missing for a found law.`);
  }
  return {
    query: text(record, "query", what),
    status,
    law,
    choices: choices.map(parseLawHit),
    message: optionalText(record, "message", what),
  };
}

async function request<T>(
  url: string,
  init: RequestInit,
  parse: (value: unknown) => T,
): Promise<LawApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(url, { ...init, cache: "no-store" });
  } catch (error: unknown) {
    if (init.signal?.aborted === true) {
      throw error;
    }
    return { ok: false, status: null, detail: `The API could not be reached at ${url}.` };
  }
  if (!response.ok) {
    return { ok: false, status: response.status, detail: await errorDetail(response) };
  }
  try {
    return { ok: true, value: parse(await response.json()) };
  } catch (error: unknown) {
    const reason = error instanceof Error ? error.message : "unreadable body";
    return { ok: false, status: response.status, detail: `Unexpected answer: ${reason}` };
  }
}

export function lawBuildUrl(slug: string): string {
  return `/api/v1/laws/${encodeURIComponent(slug)}/build`;
}

/** 422 for an empty query and 503 without a catalog come back as failures with `detail`. */
export function searchLaws(query: string, signal: AbortSignal): Promise<LawApiResult<LawSearch>> {
  return request(`/api/v1/laws/search?q=${encodeURIComponent(query)}`, { signal }, parseLawSearch);
}

/** 409 while another build runs and 404 for an unknown law come back as failures. */
export function startBuild(
  slug: string,
  steps: readonly BuildStep[],
): Promise<LawApiResult<BuildState>> {
  return request(
    lawBuildUrl(slug),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps }),
    },
    parseBuildState,
  );
}

export function readBuild(slug: string, signal: AbortSignal): Promise<LawApiResult<BuildState>> {
  return request(lawBuildUrl(slug), { signal }, parseBuildState);
}
