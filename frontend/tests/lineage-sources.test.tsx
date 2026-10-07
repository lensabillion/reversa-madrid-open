// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ClaimCard, PhraseCard } from "../components/lineage-law-browser";
import { SourceQuote } from "../components/lineage-source-quote";
import { collectSupportedClaims, prepareLineage } from "../lib/lineage";
import { indexLineageSources, safeSourceUrl } from "../lib/lineage-sources";
import { fixtureSourcesView, fixtureView } from "./lineage-fixture";

afterEach(cleanup);
const view = fixtureSourcesView();
const support = collectSupportedClaims(view).claims[0];
if (support === undefined) {
  throw new Error("Source fixture lost its supported claim");
}

test("graph evidence exposes exactly three mapped source links and metadata", () => {
  render(
    <ol>
      <ClaimCard claim={support} sources={indexLineageSources(view)} />
    </ol>,
  );
  const links = screen.getAllByRole("link");
  expect(links.map((link) => link.getAttribute("href"))).toEqual([
    view.documents?.find((document) => document.source_kind === "hys_feedback")?.url,
    view.documents?.find((document) => document.source_kind === "parltrack")?.url,
    view.documents?.find((document) => document.source_kind === "cellar")?.url,
  ]);
  expect(screen.getByRole("link", { name: "Open Parltrack dataset source" })).toBeDefined();
  expect(screen.getAllByRole("blockquote").map((quote) => quote.lastChild?.textContent)).toEqual([
    support.support.submission_span.text,
    support.support.amendment_span.text,
    support.support.final_span.text,
  ]);
  expect(screen.getByText(/field new_text/)).toBeDefined();
  expect(screen.getAllByText(/start included, end excluded/)).toHaveLength(3);
  for (const document of view.documents ?? []) {
    expect(screen.getByText(`SHA-256 ${document.sha256}`)).toBeDefined();
  }
  expect(screen.getAllByText(/retrieved/)).toHaveLength(3);
  expect(screen.getByText(/Published date unknown/)).toBeDefined();
});

test("saved evidence cards use the same source component", () => {
  const prepared = prepareLineage(view);
  const phrase = prepared.adopted[0];
  if (phrase === undefined) {
    throw new Error("Missing evidence phrase");
  }
  render(
    <ol>
      <PhraseCard phrase={phrase} sources={prepared.sources} />
    </ol>,
  );
  expect(screen.getAllByRole("link")).toHaveLength(3);
  expect(screen.getAllByText(/Unicode code-point offsets/)).toHaveLength(3);
});

test.each([
  "javascript:alert(1)",
  "data:text/html,test",
  "file:///private/tmp/source.pdf",
  "//example.org/source",
  "not a URL",
])("unsafe or invalid source URL stays unlinked: %s", (url) => {
  const source = {
    ...view,
    documents: (view.documents ?? []).map((document) => ({ ...document, url })),
  };
  render(
    <SourceQuote
      span={support.support.final_span}
      kind="verbatim"
      label="Final"
      sources={indexLineageSources(source)}
    />,
  );
  expect(screen.queryByRole("link")).toBeNull();
  expect(screen.getByText(/saved URL is not HTTP or HTTPS/)).toBeDefined();
  expect(screen.getByRole("blockquote").textContent).toContain(support.support.final_span.text);
});

test("original safe URL survives query, casing and fragment without guessed page link", () => {
  const url = "https://example.org/My%20Document.pdf?download=true#recorded-fragment";
  expect(safeSourceUrl(url)).toBe(url);
  const span = { ...support.support.final_span, page: 7 };
  const source = {
    ...view,
    documents: (view.documents ?? []).map((document) => ({ ...document, url })),
  };
  render(
    <SourceQuote span={span} kind="verbatim" label="Final" sources={indexLineageSources(source)} />,
  );
  expect(screen.getByRole("link").getAttribute("href")).toBe(url);
  expect(screen.getByText(/Recorded page 7; no page-specific URL was saved/)).toBeDefined();
});

test("legacy and missing document mappings stay explicit without inferred links", () => {
  const span = support.support.final_span;
  const { rerender } = render(
    <SourceQuote
      span={span}
      kind="verbatim"
      label="Final"
      sources={indexLineageSources(fixtureView())}
    />,
  );
  expect(screen.getByText(/this snapshot has no source metadata/)).toBeDefined();
  expect(screen.queryByRole("link")).toBeNull();
  rerender(
    <SourceQuote
      span={span}
      kind="verbatim"
      label="Final"
      sources={indexLineageSources({ ...view, documents: [] })}
    />,
  );
  expect(screen.getByText(/document metadata is missing/)).toBeDefined();
  expect(screen.queryByRole("link")).toBeNull();
});

test("explicit unavailable reason and document identity guard prevent wrong-source links", () => {
  const span = support.support.submission_span;
  const sources = {
    ...view,
    source_records: (view.source_records ?? []).map((record) =>
      record.record_id === span.record_id
        ? { ...record, document_id: "doc:wrong", unavailable_reason: null }
        : record,
    ),
  };
  const { rerender } = render(
    <SourceQuote
      span={span}
      kind="verbatim"
      label="Submission"
      sources={indexLineageSources(sources)}
    />,
  );
  expect(screen.getByText(/source identity or record field does not match/)).toBeDefined();
  expect(screen.queryByRole("link")).toBeNull();
  rerender(
    <SourceQuote
      span={span}
      kind="verbatim"
      label="Submission"
      sources={indexLineageSources({
        ...view,
        source_records: (view.source_records ?? []).map((record) => ({
          ...record,
          unavailable_reason: "Source file was not collected",
        })),
      })}
    />,
  );
  expect(screen.getByText(/Source file was not collected/)).toBeDefined();
  expect(screen.queryByRole("link")).toBeNull();
});

test("field guard and code-point offsets preserve Unicode quote identity", () => {
  const span = { ...support.support.final_span, text: "🧭 café", start: 10, end: 16 };
  const { rerender } = render(
    <SourceQuote span={span} kind="verbatim" label="Final" sources={indexLineageSources(view)} />,
  );
  expect(within(screen.getByRole("blockquote")).getByText(/🧭 café/)).toBeDefined();
  expect(screen.getByText(/\[10, 16\)/)).toBeDefined();
  rerender(
    <SourceQuote
      span={{ ...span, field: "new_text" }}
      kind="verbatim"
      label="Final"
      sources={indexLineageSources(view)}
    />,
  );
  expect(screen.getByText(/source identity or record field does not match/)).toBeDefined();
  expect(screen.queryByRole("link")).toBeNull();
});

test("duplicate document and record IDs fail explicitly", () => {
  expect(() =>
    indexLineageSources({
      ...view,
      documents: [...(view.documents ?? []), ...(view.documents ?? [])],
    }),
  ).toThrow("Duplicate source metadata identifiers");
  expect(() =>
    indexLineageSources({
      ...view,
      source_records: [...(view.source_records ?? []), ...(view.source_records ?? [])],
    }),
  ).toThrow("Duplicate source metadata identifiers");
});

test("article sources follow explicit document mapping, never a record-ID guess", () => {
  const document = view.documents?.find((item) => item.source_kind === "cellar");
  if (document === undefined) {
    throw new Error("Missing source document");
  }
  const renamed = {
    ...view,
    documents: (view.documents ?? []).map((item) =>
      item === document
        ? {
            ...item,
            document_id: "doc:archive:exact-source",
            url: "https://example.org/actual-recorded-source",
          }
        : item,
    ),
    source_records: (view.source_records ?? []).map((record) =>
      record.document_id === document.document_id
        ? { ...record, document_id: "doc:archive:exact-source" }
        : record,
    ),
  };
  render(
    <SourceQuote
      span={support.support.final_span}
      kind="verbatim"
      label="Final"
      sources={indexLineageSources(renamed)}
    />,
  );
  expect(screen.getByRole("link").getAttribute("href")).toBe(
    "https://example.org/actual-recorded-source",
  );
  expect(screen.getByText("doc:archive:exact-source")).toBeDefined();
});

test("all seven saved carriers can be expanded with their own exact quote and source", () => {
  const base = view.adoptions[0];
  const phrase = view.adopted_phrases[0];
  const evidence = base?.evidence?.[0];
  if (base === undefined || phrase === undefined || evidence === undefined) {
    throw new Error("Missing fixture carrier");
  }
  const carriers = Array.from({ length: 7 }, (_, index) => {
    const id = `am:carrier:${index}`;
    const quotation = `Carrier ${index}: ${evidence.amendment_span.text}`;
    const ownEvidence = {
      ...evidence,
      evidence_id: `evidence:carrier:${index}`,
      amendment_span: {
        ...evidence.amendment_span,
        record_id: id,
        text: quotation,
        end: evidence.amendment_span.start + [...quotation].length,
      },
    };
    return { ...base, amendment_id: id, evidence: [ownEvidence] };
  });
  // Context-card fixture intentionally has no origin joins; the adapter must not construct them.
  const context = {
    ...view,
    origins: [],
    adoptions: carriers,
    source_records: [
      ...(view.source_records ?? []).filter((record) => record.record_type === "article"),
      ...carriers.map((carrier) => ({
        record_id: carrier.amendment_id,
        document_id: "doc:parltrack:ep_amendments",
        record_type: "amendment" as const,
        label: carrier.amendment_id,
        unavailable_reason: null,
      })),
    ],
  };
  const prepared = prepareLineage(context);
  const row = prepared.adopted[0];
  if (row === undefined) {
    throw new Error("Missing row");
  }
  render(
    <ol>
      <PhraseCard phrase={row} sources={prepared.sources} />
    </ol>,
  );
  expect(screen.queryByText(/Carrier 6:/)).toBeNull();
  expect(screen.getAllByRole("link", { name: "Open Parltrack dataset source" })).toHaveLength(6);
  expect(
    screen.getByText(/does not assert that every submission matches every carrier/),
  ).toBeDefined();
  const expand = screen.getByRole("button", { name: "Show all 7 carriers" });
  fireEvent.click(expand);
  expect(screen.getAllByRole("link", { name: "Open Parltrack dataset source" })).toHaveLength(7);
  expect(screen.getByText(/Carrier 6:/)).toBeDefined();
  expect(screen.getByText(/Saved adoption evidence evidence:carrier:6/)).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Show fewer carriers" }));
  expect(screen.queryByText(/Carrier 6:/)).toBeNull();
});

test("each prepared carrier keeps evidence only for its own phrase", () => {
  const base = view.adoptions[0];
  const first = view.adopted_phrases[0];
  const evidence = base?.evidence?.[0];
  if (base === undefined || first === undefined || evidence === undefined) {
    throw new Error("Missing fixture");
  }
  const second = { ...first, phrase_id: "phrase:second" };
  const secondEvidence = {
    ...evidence,
    evidence_id: "evidence:second",
    phrase_id: second.phrase_id,
  };
  const prepared = prepareLineage({
    ...view,
    adopted_phrases: [first, second],
    adoptions: [
      {
        ...base,
        phrase_ids: [first.phrase_id, second.phrase_id],
        evidence: [evidence, secondEvidence],
      },
    ],
  });
  for (const row of prepared.adopted) {
    expect(row.amendments[0]?.evidence.map((item) => item.phrase_id)).toEqual([row.phraseId]);
  }
});

test("legacy carrier rows explicitly lack exact quotation evidence", () => {
  const prepared = prepareLineage(fixtureView());
  const row = prepared.adopted[0];
  if (row === undefined) {
    throw new Error("Missing legacy row");
  }
  render(
    <ol>
      <PhraseCard phrase={row} sources={prepared.sources} />
    </ol>,
  );
  expect(screen.getByText("Exact carrier quotation unavailable in this snapshot.")).toBeDefined();
  expect(screen.getAllByRole("blockquote")).toHaveLength(2);
  expect(screen.queryByText("→")).toBeNull();
});
