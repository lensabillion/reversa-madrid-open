import { AtlasApiError, atlasViewUrl, readAtlasJson } from "./atlas-api";

/**
 * `GET /api/v1/atlas/{slug}/findings`: the public report's five questions for one law, split
 * into a headline, details, evidence references and a limitation. The Python source of truth
 * is `backend/src/influence/schemas/findings.py`; every line is the report's own, so the
 * explorer computes nothing and shows the same numbers as `make report`.
 */

export const findingQuestions = ["WHO", "WHAT", "TOWARDS", "HOW", "NEXT"] as const;
export type FindingQuestion = (typeof findingQuestions)[number];

/** A file under the data root and, when the report names it, the field holding the rows. */
export interface FindingEvidence {
  file: string;
  field: string | null;
}

/** `computed`: a file the question reads is written; `not_run`: `command` writes it. */
export type FindingStatus = "computed" | "not_run";

export interface AtlasFinding {
  question: FindingQuestion;
  title: string;
  status: FindingStatus;
  headline: string | null;
  details: readonly string[];
  evidence: readonly FindingEvidence[];
  limitation: string;
  command: string | null;
  /** Each input that is missing or invalid, with the command that writes it. */
  notes: readonly string[];
}

export interface AtlasLawFindings {
  schema_version: "findings-1";
  procedure_id: string;
  slug: string;
  title: string;
  run_id: string;
  findings: readonly AtlasFinding[];
}

/** A law that was never collected answers 404: an expected state, not a failure to load. */
export type AtlasFindingsResult =
  | { found: true; findings: AtlasLawFindings }
  | { found: false; detail: string };

export function atlasFindingsUrl(slug: string): string {
  return `${atlasViewUrl(slug)}/findings`;
}

function invalid(path: string, expected: string): never {
  throw new Error(`Invalid findings data: ${path} must be ${expected}.`);
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
  return value === null ? null : text(value, path);
}

function list<T>(value: unknown, path: string, item: (value: unknown, path: string) => T): T[] {
  if (!Array.isArray(value)) {
    return invalid(path, "a list");
  }
  return value.map((entry: unknown, index) => item(entry, `${path}[${index}]`));
}

function question(value: unknown, path: string): FindingQuestion {
  const known = findingQuestions.find((name) => name === value);
  return known ?? invalid(path, findingQuestions.join(", "));
}

function status(value: unknown, path: string): FindingStatus {
  return value === "computed" || value === "not_run" ? value : invalid(path, "computed or not_run");
}

function evidence(value: unknown, path: string): FindingEvidence {
  const row = record(value, path);
  return { file: text(row.file, `${path}.file`), field: textOrNull(row.field, `${path}.field`) };
}

function finding(value: unknown, path: string): AtlasFinding {
  const row = record(value, path);
  return {
    question: question(row.question, `${path}.question`),
    title: text(row.title, `${path}.title`),
    status: status(row.status, `${path}.status`),
    headline: textOrNull(row.headline, `${path}.headline`),
    details: list(row.details, `${path}.details`, text),
    evidence: list(row.evidence, `${path}.evidence`, evidence),
    limitation: text(row.limitation, `${path}.limitation`),
    command: textOrNull(row.command, `${path}.command`),
    notes: list(row.notes, `${path}.notes`, text),
  };
}

/** Checks the response against the backend's `LawFindings`; throws on the first broken field. */
export function lawFindings(value: unknown): AtlasLawFindings {
  const row = record(value, "the response");
  if (row.schema_version !== "findings-1") {
    throw new Error(`Unsupported findings schema: ${String(row.schema_version)}`);
  }
  return {
    schema_version: "findings-1",
    procedure_id: text(row.procedure_id, "procedure_id"),
    slug: text(row.slug, "slug"),
    title: text(row.title, "title"),
    run_id: text(row.run_id, "run_id"),
    findings: list(row.findings, "findings", finding),
  };
}

/** Reads one law's findings; a 404 (never collected) is a result, every other failure throws. */
export async function readAtlasFindings(
  url: string,
  signal: AbortSignal,
): Promise<AtlasFindingsResult> {
  try {
    return { found: true, findings: lawFindings(await readAtlasJson<unknown>(url, signal)) };
  } catch (error: unknown) {
    if (error instanceof AtlasApiError && error.status === 404) {
      return { found: false, detail: error.detail };
    }
    throw error;
  }
}

/** The report's Markdown code marks, dropped for display; the words stay as written. */
export function plainFinding(line: string): string {
  return line.replaceAll("`", "").replaceAll("**", "");
}

/** One short line naming the files (and fields) a finding was read from. */
export function evidenceLine(evidence: readonly FindingEvidence[]): string {
  return evidence
    .map((ref) => (ref.field === null ? ref.file : `${ref.file}, field ${ref.field}`))
    .join("; ");
}
