import type { AtlasEvidenceProps, AtlasExcerpt } from "../components/atlas-evidence";
import type { AtlasLinkView } from "../components/atlas-explorer";

/** Serialized projections of backend/schemas/atlas.py, not a decoder for arbitrary JSON. */
interface AtlasRecord {
  schema_version: "atlas-1";
}
type SpanField = "text" | "old_text" | "new_text" | "justification";
export interface AtlasSourceSpan {
  record_id: string;
  field: SpanField;
  start: number;
  end: number;
  text: string;
  page: number | null;
}
interface Law extends AtlasRecord {
  procedure_id: string;
  title: string;
  subjects: readonly string[];
}
interface Document extends AtlasRecord {
  document_id: string;
  procedure_id: string | null;
  url: string;
  title: string | null;
  published_at: string | null;
  language: string | null;
}
interface DocumentText extends AtlasRecord {
  document_id: string;
  text: string;
}
interface Passage extends AtlasRecord {
  passage_id: string;
  procedure_id: string;
  document_id: string;
  actor_id: string;
  span: AtlasSourceSpan;
}
interface Actor extends AtlasRecord {
  actor_id: string;
  name: string;
}
interface Ask extends AtlasRecord {
  ask_id: string;
  procedure_id: string;
  actor_id: string;
  joint_actor_ids: readonly string[];
  document_id: string;
  passage_id: string | null;
  span: AtlasSourceSpan;
  requested_change: string | null;
  language: string | null;
}
interface Amendment extends AtlasRecord {
  amendment_id: string;
  procedure_id: string;
  document_id: string;
  old_text: string | null;
  new_text: string;
  justification: string | null;
  language: string | null;
}
interface Article extends AtlasRecord {
  article_id: string;
  procedure_id: string;
  document_id: string;
  stage: "proposal" | "parliament_position" | "final_act";
  text: string;
}
interface Assessment extends AtlasRecord {
  link_id: string;
  procedure_id: string;
  amendment_id: string;
  ask_id: string;
  status: AtlasEvidenceProps["assessment"]["status"];
  tier: "copied" | "reworded" | "same_direction" | null;
  support_score: number;
  amendment_spans: readonly AtlasSourceSpan[];
  ask_spans: readonly AtlasSourceSpan[];
  time_eligibility: "ask_first" | "amendment_first" | "unknown_date";
  method: string;
  method_revision: string;
  limitations: readonly string[];
}
interface Outcome extends AtlasRecord {
  outcome_id: string;
  procedure_id: string;
  ask_id: string;
  link_id: string | null;
  amendment_id: string | null;
  relation: "via_amendment" | "direct_to_final";
  stage: "heard" | "parliament_position" | "final_act";
  result: AtlasEvidenceProps["outcome"]["status"];
  kind: "wording" | "reworded" | "deletion" | "status_quo" | null;
  article_id: string | null;
  spans: readonly AtlasSourceSpan[];
  reason: string | null;
  method: string;
}

/** Schema-validated serialized atlas-1 records. Join/span checks also run at this boundary. */
export interface AtlasBundle {
  laws: readonly Law[];
  documents: readonly Document[];
  documentTexts: readonly DocumentText[];
  passages: readonly Passage[];
  actors: readonly Actor[];
  asks: readonly Ask[];
  amendments: readonly Amendment[];
  articles: readonly Article[];
  links: readonly Assessment[];
  outcomes: readonly Outcome[];
}

function index<T extends AtlasRecord>(rows: readonly T[], key: (row: T) => string): Map<string, T> {
  const result = new Map<string, T>();
  for (const row of rows) {
    if (row.schema_version !== "atlas-1") {
      throw new Error(`Unsupported Atlas schema: ${row.schema_version}`);
    }
    const id = key(row);
    if (result.has(id)) {
      throw new Error(`Duplicate Atlas record: ${id}`);
    }
    result.set(id, row);
  }
  return result;
}

function required<T>(records: ReadonlyMap<string, T>, id: string): T {
  const record = records.get(id);
  if (record === undefined) {
    throw new Error(`Missing Atlas record: ${id}`);
  }
  return record;
}

function sameLaw(actual: string | null, expected: string, id: string): void {
  if (actual !== null && actual !== expected) {
    throw new Error(`Procedure mismatch for ${id}: ${actual} versus ${expected}`);
  }
}

interface TextRecord {
  documentId: string;
  fields: Partial<Record<SpanField, string | null>>;
}
interface ResolvedSpan {
  recordId: string;
  field: SpanField;
  documentId: string;
  sourceText: string;
  start: number;
  end: number;
  text: string;
  page: number | null;
}

function assertQuote(span: AtlasSourceSpan, text: string): void {
  const characters = Array.from(text);
  if (
    !Number.isInteger(span.start) ||
    !Number.isInteger(span.end) ||
    span.start < 0 ||
    span.end <= span.start ||
    span.end > characters.length ||
    characters.slice(span.start, span.end).join("") !== span.text
  ) {
    throw new Error(`Invalid source quote: ${span.record_id}.${span.field}`);
  }
}

/**
 * Join pipeline decisions to display props; never select a winner or calculate rankings.
 * Produces one card per assessment, with joint actors named together. The year is the
 * procedure-reference year, not an inferred amendment/publication date. Indexing is O(R);
 * quote checks scan their source text in O(T) per span (one law's records at a time).
 * Multi-record evidence that cannot fit one source column fails explicitly, never truncates.
 */
export function atlasLinkViews(bundle: AtlasBundle): AtlasLinkView[] {
  const laws = index(bundle.laws, (row) => row.procedure_id);
  const documents = index(bundle.documents, (row) => row.document_id);
  const documentTexts = index(bundle.documentTexts, (row) => row.document_id);
  const passages = index(bundle.passages, (row) => row.passage_id);
  const actors = index(bundle.actors, (row) => row.actor_id);
  const asks = index(bundle.asks, (row) => row.ask_id);
  const amendments = index(bundle.amendments, (row) => row.amendment_id);
  const articles = index(bundle.articles, (row) => row.article_id);
  const links = index(bundle.links, (row) => row.link_id);
  const outcomes = index(bundle.outcomes, (row) => row.outcome_id);
  const texts = new Map<string, TextRecord>();
  for (const row of documentTexts.values()) {
    required(documents, row.document_id);
    texts.set(row.document_id, { documentId: row.document_id, fields: { text: row.text } });
  }
  for (const row of amendments.values()) {
    texts.set(row.amendment_id, {
      documentId: row.document_id,
      fields: { old_text: row.old_text, new_text: row.new_text, justification: row.justification },
    });
  }
  for (const row of articles.values()) {
    texts.set(row.article_id, { documentId: row.document_id, fields: { text: row.text } });
  }

  function resolve(span: AtlasSourceSpan, visiting: ReadonlySet<string> = new Set()): ResolvedSpan {
    if (visiting.has(span.record_id)) {
      throw new Error(`Cyclic source passage: ${span.record_id}`);
    }
    const passage = passages.get(span.record_id);
    if (passage) {
      if (span.field !== "text") {
        throw new Error(`Invalid passage field: ${span.field}`);
      }
      const source = resolve(passage.span, new Set([...visiting, span.record_id]));
      if (source.documentId !== passage.document_id) {
        throw new Error(`Passage source mismatch: ${passage.passage_id}`);
      }
      assertQuote(span, passage.span.text);
      return {
        ...source,
        start: source.start + span.start,
        end: source.start + span.end,
        text: span.text,
        page: span.page ?? source.page,
      };
    }
    const source = required(texts, span.record_id);
    const text = source.fields[span.field];
    if (text === null || text === undefined) {
      throw new Error(`Source field unavailable: ${span.record_id}.${span.field}`);
    }
    required(documents, source.documentId);
    assertQuote(span, text);
    return { ...span, recordId: span.record_id, documentId: source.documentId, sourceText: text };
  }

  function excerpt(
    recordId: string,
    field: SpanField,
    spans: readonly ResolvedSpan[],
    procedureId: string,
    language: string | null,
  ): AtlasExcerpt {
    const source = required(texts, recordId);
    const text = source.fields[field];
    if (text === null || text === undefined) {
      throw new Error(`Source field unavailable: ${recordId}.${field}`);
    }
    const document = required(documents, source.documentId);
    sameLaw(document.procedure_id, procedureId, document.document_id);
    for (const span of spans) {
      if (span.recordId !== recordId || span.field !== field) {
        throw new Error(
          `Evidence spans name different source records/fields: ${recordId}.${field}`,
        );
      }
    }
    const pages = new Set(spans.map((span) => span.page));
    return {
      text,
      language: language ?? document.language ?? "und",
      spans: spans.map(({ start, end, text: quote }) => ({ start, end, text: quote })),
      source: {
        title: document.title ?? document.document_id,
        url: document.url,
        page: pages.size === 1 ? (spans[0]?.page ?? null) : null,
        publishedAt: document.published_at,
      },
    };
  }

  const finalOutcomes = new Map<string, Outcome>();
  for (const outcome of outcomes.values()) {
    const ask = required(asks, outcome.ask_id);
    sameLaw(outcome.procedure_id, ask.procedure_id, outcome.outcome_id);
    if (outcome.link_id !== null) {
      const link = required(links, outcome.link_id);
      if (link.ask_id !== outcome.ask_id || link.amendment_id !== outcome.amendment_id) {
        throw new Error(`Outcome link mismatch: ${outcome.outcome_id}`);
      }
    }
    if (outcome.amendment_id !== null) {
      sameLaw(
        required(amendments, outcome.amendment_id).procedure_id,
        ask.procedure_id,
        outcome.outcome_id,
      );
    }
    if (outcome.article_id !== null) {
      const article = required(articles, outcome.article_id);
      sameLaw(article.procedure_id, ask.procedure_id, article.article_id);
      if (article.stage !== outcome.stage) {
        throw new Error(`Outcome article stage mismatch: ${outcome.outcome_id}`);
      }
    }
    for (const span of outcome.spans) {
      resolve(span);
    }
    if (outcome.stage === "final_act") {
      if (finalOutcomes.has(outcome.ask_id)) {
        throw new Error(`Ambiguous final outcome for ask: ${outcome.ask_id}`);
      }
      finalOutcomes.set(outcome.ask_id, outcome);
    }
  }

  return [...links.values()].map((link) => {
    const law = required(laws, link.procedure_id);
    const ask = required(asks, link.ask_id);
    const amendment = required(amendments, link.amendment_id);
    sameLaw(ask.procedure_id, link.procedure_id, ask.ask_id);
    sameLaw(amendment.procedure_id, link.procedure_id, amendment.amendment_id);
    const anchor = resolve(ask.span);
    if (anchor.documentId !== ask.document_id) {
      throw new Error(`Ask source mismatch: ${ask.ask_id}`);
    }
    if (ask.passage_id !== null) {
      const passage = required(passages, ask.passage_id);
      sameLaw(passage.procedure_id, ask.procedure_id, passage.passage_id);
      if (passage.document_id !== ask.document_id || passage.actor_id !== ask.actor_id) {
        throw new Error(`Ask passage mismatch: ${ask.ask_id}`);
      }
      resolve(passage.span);
    }
    const askSpans = link.ask_spans.map((span) => resolve(span));
    for (const span of askSpans) {
      if (
        span.recordId !== anchor.recordId ||
        span.field !== anchor.field ||
        span.start < anchor.start ||
        span.end > anchor.end
      ) {
        throw new Error(`Link quote lies outside its ask: ${link.link_id}`);
      }
    }
    const amendmentSpans = link.amendment_spans.map((span) => resolve(span));
    for (const span of amendmentSpans) {
      if (
        span.recordId !== amendment.amendment_id ||
        !["old_text", "new_text"].includes(span.field)
      ) {
        throw new Error(`Amendment evidence must name its old_text/new_text: ${link.link_id}`);
      }
    }
    const oldSpans = amendmentSpans.filter((span) => span.field === "old_text");
    const newSpans = amendmentSpans.filter((span) => span.field === "new_text");
    const outcome = finalOutcomes.get(ask.ask_id);
    let finalText: AtlasExcerpt | null = null;
    if (outcome) {
      const spans = outcome.spans.map((span) => resolve(span));
      const first = spans[0];
      if (outcome.article_id !== null) {
        finalText = excerpt(outcome.article_id, "text", spans, law.procedure_id, null);
      } else if (first) {
        finalText = excerpt(first.recordId, first.field, spans, law.procedure_id, null);
      }
    }
    const names = [...new Set([ask.actor_id, ...ask.joint_actor_ids])].map(
      (id) => required(actors, id).name,
    );
    const year = /^\d{4}\//.test(law.procedure_id) ? Number(law.procedure_id.slice(0, 4)) : NaN;
    if (!Number.isInteger(year)) {
      throw new Error(`Invalid procedure reference: ${law.procedure_id}`);
    }
    return {
      id: link.link_id,
      law: law.title,
      topics: law.subjects.length > 0 ? law.subjects : ["Topic unknown"],
      year,
      evidence: {
        actor: names.length > 1 ? `Joint ask: ${names.join("; ")}` : names.join(""),
        ask: ask.requested_change ?? ask.span.text,
        assessment: {
          status: link.status,
          method: `${link.method} (${link.method_revision}); chronology: ${link.time_eligibility}; support score: ${link.support_score} (not a probability)`,
          explanation: {
            published:
              "The assessment supports a connection between this request and this amendment. Compare the highlighted wording below.",
            unconfirmed:
              "This is a possible match that has not met the standard for a published connection.",
            contradicted:
              "The assessment found evidence against this proposed connection. It is excluded from the published graph.",
            insufficient_evidence:
              "There is not enough evidence to establish this connection. It is excluded from the published graph.",
          }[link.status],
          limitations: link.limitations,
        },
        submission: excerpt(
          anchor.recordId,
          anchor.field,
          askSpans.length > 0 ? askSpans : [anchor],
          law.procedure_id,
          ask.language,
        ),
        original:
          amendment.old_text === null
            ? null
            : excerpt(
                amendment.amendment_id,
                "old_text",
                oldSpans,
                law.procedure_id,
                amendment.language,
              ),
        amendment: excerpt(
          amendment.amendment_id,
          "new_text",
          newSpans,
          law.procedure_id,
          amendment.language,
        ),
        outcome: {
          status: outcome?.result ?? "unknown",
          explanation: outcome
            ? `${outcome.relation === "direct_to_final" ? "Direct ask-to-final assessment; no amendment attribution. " : ""}${outcome.reason ?? `Pipeline final-act result: ${outcome.result}.`}`
            : "No final-act outcome was supplied.",
          finalText,
        },
      },
    };
  });
}
