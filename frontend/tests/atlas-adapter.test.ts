// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, expect, test } from "vitest";
import { AtlasExplorer } from "../components/atlas-explorer";
import { type AtlasBundle, atlasLinkViews } from "../lib/atlas";

/** Committed fixtures are generated and validated by the authoritative Python contracts. */
function records<T>(name: string): T[] {
  return readFileSync(
    resolve(process.cwd(), "../backend/tests/fixtures/atlas", `${name}.jsonl`),
    "utf8",
  )
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line) as T);
}
function fixture(): AtlasBundle {
  return {
    laws: records("laws"),
    documents: records("documents"),
    documentTexts: records("document_texts"),
    passages: records("passages"),
    actors: records("actors"),
    asks: records("asks"),
    amendments: records("amendments"),
    articles: records("articles"),
    links: records("links"),
    outcomes: records("outcomes"),
  };
}
function first<T>(rows: readonly T[]): T {
  const row = rows[0];
  if (row === undefined) {
    throw new Error("Fixture record missing");
  }
  return row;
}
afterEach(cleanup);

test("joins shared atlas-1 fixtures, provenance and exact fields without inferring results", () => {
  const bundle = fixture();
  const views = atlasLinkViews(bundle);
  expect(views).toHaveLength(6);
  const copy = first(views);
  expect(copy.id).toBe("link:a-am1-makers");
  expect(copy.year).toBe(2099);
  expect(copy.topics).toEqual(["3.40.06 Electronics", "4.60.08 Safety of products"]);
  expect(copy.evidence.actor).toBe("Widget Makers Europe");
  expect(copy.evidence.submission.spans).toEqual([
    { start: 97, end: 120, text: "for at least six months" },
  ]);
  expect(copy.evidence.submission.text).toBe(first(bundle.documentTexts).text);
  expect(copy.evidence.submission.source).toEqual({
    title: "doc:hys_feedback:9000001",
    url: "https://example.invalid/fixture/feedback/9000001",
    page: null,
    publishedAt: "2099-02-01T12:00:00Z",
  });
  expect(copy.evidence.amendment.spans).toEqual([
    { start: 36, end: 59, text: "for at least six months" },
  ]);
  expect(copy.evidence.outcome.status).toBe("full");
  expect(copy.evidence.outcome.finalText?.source.url).toContain("32099R0001");
  expect(views.find((view) => view.id === "link:a-am2-city")?.evidence.outcome.status).toBe(
    "partial",
  );
  expect(
    views.find((view) => view.id === "link:a-am1-undated")?.evidence.submission.source.publishedAt,
  ).toBeNull();
  expect(
    views.find((view) => view.id === "link:a-am1-undated")?.evidence.outcome.explanation,
  ).toContain("no amendment attribution");
  const missing = views.find((view) => view.id === "link:b-am3-labels");
  expect(missing?.evidence.outcome).toEqual({
    status: "unknown",
    explanation: "No final act: the procedure is still being negotiated.",
    finalText: null,
  });
});

test("all four pipeline statuses retain published/audit isolation in the consumer", () => {
  const views = atlasLinkViews(fixture());
  expect(new Set(views.map((view) => view.evidence.assessment.status))).toEqual(
    new Set(["published", "unconfirmed", "contradicted", "insufficient_evidence"]),
  );
  render(createElement(AtlasExplorer, { links: views, coverageNotes: [] }));
  expect(screen.getByRole("status").textContent).toBe("2 of 2 published links shown");
  expect(screen.queryByRole("button", { name: /Acme/ })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Audit candidates" }));
  expect(screen.getByRole("status").textContent).toBe("4 of 4 audit candidates shown");
  fireEvent.click(screen.getByRole("button", { name: /Acme/ }));
  expect(screen.getByText("Insufficient evidence")).toBeDefined();
  expect(screen.queryByText("Published link")).toBeNull();
});

test("Unicode source offsets and passage-relative highlights resolve to original document text", () => {
  const bundle = fixture();
  const doc = first(bundle.documentTexts);
  const ask = first(bundle.asks);
  const passage = first(bundle.passages);
  const link = first(bundle.links);
  const prefix = "😀 ";
  const shifted = {
    ...bundle,
    documentTexts: bundle.documentTexts.map((row) =>
      row.document_id === doc.document_id ? { ...row, text: prefix + row.text } : row,
    ),
    asks: bundle.asks.map((row) =>
      row.ask_id === ask.ask_id
        ? { ...row, span: { ...row.span, start: row.span.start + 2, end: row.span.end + 2 } }
        : row,
    ),
    passages: bundle.passages.map((row) =>
      row.passage_id === passage.passage_id
        ? { ...row, span: { ...row.span, start: row.span.start + 2, end: row.span.end + 2 } }
        : row,
    ),
    links: bundle.links.map((row) =>
      row.link_id === link.link_id
        ? {
            ...row,
            ask_spans: row.ask_spans.map((span) => ({
              ...span,
              record_id: passage.passage_id,
              start: span.start - passage.span.start,
              end: span.end - passage.span.start,
              page: 3,
            })),
          }
        : row,
    ),
  };
  const excerpt = first(atlasLinkViews(shifted)).evidence.submission;
  expect(excerpt.text).toBe(prefix + doc.text);
  expect(excerpt.spans).toEqual([{ start: 99, end: 122, text: "for at least six months" }]);
  expect(excerpt.source.page).toBe(3);
});

test("known empty and missing originals stay distinct; deletion evidence stays in old_text", () => {
  const bundle = fixture();
  const amendment = first(bundle.amendments);
  const variants = [null, ""];
  for (const old_text of variants) {
    const changed = {
      ...bundle,
      amendments: bundle.amendments.map((row) =>
        row.amendment_id === amendment.amendment_id ? { ...row, old_text } : row,
      ),
    };
    expect(first(atlasLinkViews(changed)).evidence.original?.text ?? null).toBe(old_text);
  }
  const quote = "Providers";
  const changed = {
    ...bundle,
    amendments: bundle.amendments.map((row) =>
      row.amendment_id === amendment.amendment_id ? { ...row, new_text: "" } : row,
    ),
    links: bundle.links.map((row) =>
      row.amendment_id === amendment.amendment_id
        ? {
            ...row,
            amendment_spans: [
              {
                record_id: amendment.amendment_id,
                field: "old_text" as const,
                start: 0,
                end: quote.length,
                text: quote,
                page: null,
              },
            ],
          }
        : row,
    ),
    outcomes: bundle.outcomes.filter((row) => row.stage === "final_act"),
  };
  const evidence = first(atlasLinkViews(changed)).evidence;
  expect(evidence.amendment.text).toBe("");
  expect(evidence.original?.spans).toEqual([{ start: 0, end: 9, text: "Providers" }]);
});

test("selects final_act only, never upgrades a heard or Parliament result into a final win", () => {
  const bundle = fixture();
  const withoutFinal = {
    ...bundle,
    outcomes: bundle.outcomes.filter((row) => row.stage !== "final_act"),
  };
  expect(first(atlasLinkViews(withoutFinal)).evidence.outcome).toEqual({
    status: "unknown",
    explanation: "No final-act outcome was supplied.",
    finalText: null,
  });
  const final = bundle.outcomes.find((row) => row.stage === "final_act");
  if (!final) {
    throw new Error("Final fixture missing");
  }
  expect(() =>
    atlasLinkViews({
      ...bundle,
      outcomes: [...bundle.outcomes, { ...final, outcome_id: "outcome:duplicate" }],
    }),
  ).toThrow("Ambiguous final outcome");
});

test("joint actors retain attribution without duplicating links", () => {
  const bundle = fixture();
  const ask = first(bundle.asks);
  const changed = {
    ...bundle,
    asks: bundle.asks.map((row) =>
      row.ask_id === ask.ask_id
        ? { ...row, joint_actor_ids: [row.actor_id, "actor:tr:234567890123-45"] }
        : row,
    ),
  };
  const views = atlasLinkViews(changed);
  expect(views).toHaveLength(bundle.links.length);
  expect(first(views).evidence.actor).toBe("Joint ask: Widget Makers Europe; Consumer Watch");
});

test("rejects an exact same-document quote outside the requested ask", () => {
  const bundle = fixture();
  const link = first(bundle.links);
  const quote = "Widget Makers Europe";
  expect(() =>
    atlasLinkViews({
      ...bundle,
      links: bundle.links.map((row) =>
        row.link_id === link.link_id
          ? {
              ...row,
              ask_spans: [{ ...first(row.ask_spans), start: 0, end: quote.length, text: quote }],
            }
          : row,
      ),
    }),
  ).toThrow("Link quote lies outside its ask");
});

test("rejects a passage assigned to a different actor even when its text and document match", () => {
  const bundle = fixture();
  const passage = first(bundle.passages);
  expect(() =>
    atlasLinkViews({
      ...bundle,
      passages: bundle.passages.map((row) =>
        row.passage_id === passage.passage_id
          ? { ...row, actor_id: "actor:tr:234567890123-45" }
          : row,
      ),
    }),
  ).toThrow("Ask passage mismatch");
});

test("missing law subjects remain an explicit unknown topic", () => {
  const bundle = fixture();
  expect(
    first(atlasLinkViews({ ...bundle, laws: bundle.laws.map((law) => ({ ...law, subjects: [] })) }))
      .topics,
  ).toEqual(["Topic unknown"]);
});

test.each(["quote", "record", "field", "document", "procedure", "actor", "stage"])(
  "rejects %s corruption explicitly",
  (kind) => {
    const bundle = fixture();
    const link = first(bundle.links);
    const span = first(link.ask_spans);
    let changed: AtlasBundle = bundle;
    switch (kind) {
      case "quote":
        changed = {
          ...bundle,
          links: bundle.links.map((row) =>
            row.link_id === link.link_id
              ? { ...row, ask_spans: [{ ...span, text: "invented" }] }
              : row,
          ),
        };
        break;
      case "record":
        changed = {
          ...bundle,
          links: bundle.links.map((row) =>
            row.link_id === link.link_id
              ? { ...row, ask_spans: [{ ...span, record_id: "doc:hys_feedback:missing" }] }
              : row,
          ),
        };
        break;
      case "field":
        changed = {
          ...bundle,
          links: bundle.links.map((row) =>
            row.link_id === link.link_id
              ? { ...row, ask_spans: [{ ...span, field: "new_text" }] }
              : row,
          ),
        };
        break;
      case "document":
        changed = {
          ...bundle,
          documents: bundle.documents.filter(
            (row) => row.document_id !== first(bundle.asks).document_id,
          ),
        };
        break;
      case "procedure":
        changed = {
          ...bundle,
          asks: bundle.asks.map((row) =>
            row.ask_id === link.ask_id ? { ...row, procedure_id: "2099/0002(COD)" } : row,
          ),
        };
        break;
      case "actor":
        changed = {
          ...bundle,
          actors: bundle.actors.filter((row) => row.actor_id !== first(bundle.asks).actor_id),
        };
        break;
      case "stage":
        changed = {
          ...bundle,
          articles: bundle.articles.map((row) =>
            row.stage === "final_act" ? { ...row, stage: "proposal" } : row,
          ),
        };
        break;
      default:
        throw new Error(`Unexpected test case: ${kind}`);
    }
    expect(() => atlasLinkViews(changed)).toThrow();
  },
);
