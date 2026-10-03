"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import type { AtlasSourceSpan } from "../lib/atlas";
import { AtlasApiError } from "../lib/atlas-api";
import {
  type LineageCreditRow,
  type LineageCreditTable,
  type LineageOriginRow,
  type LineagePhraseRow,
  type PreparedLineage,
  prepareLineage,
} from "../lib/lineage";
import {
  type LineageLawSummary,
  type LineageView,
  lineageLawsUrl,
  lineageViewUrl,
  readLineageLaws,
  readLineageView,
} from "../lib/lineage-api";
import {
  anyPhrase,
  filterPhrases,
  type LineageChannels,
  lineageChannels,
  linkPool,
  type OrganisationRanking,
  type PhraseFilter,
  phraseFacets,
  rankOrganisations,
} from "../lib/lineage-insights";
import { useResource } from "../lib/use-resource";
import { coverageNote, retryStyle, StateMessage, sentence } from "./atlas-law-browser";
import { Channels, FiveQuestions, LinkCheck, questionsFor, WhoShaped } from "./lineage-insights";

const buildCommand = "make lineage LAW='2021/0106(COD)'";
/** Phrases shown before "Show more"; the AI Act has hundreds, and each card is tall. */
export const PHRASES_PER_PAGE = 20;
const CREDITS_SHOWN = 15;
/** Wording copied into many amendments would make one card very tall; the rest are counted. */
const AMENDMENTS_PER_CARD = 6;
const eyebrow = "text-[11px] font-semibold uppercase tracking-[0.13em] text-stone-600";

const count = new Intl.NumberFormat("en-US");
const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });

/** A law without a lineage view is an expected answer here, not a failure to load. */
type LawViewResult = { found: true; view: LineageView } | { found: false; detail: string };

async function readLawView(url: string, signal: AbortSignal): Promise<LawViewResult> {
  try {
    return { found: true, view: await readLineageView(url, signal) };
  } catch (error: unknown) {
    if (error instanceof AtlasApiError && error.status === 404) {
      return { found: false, detail: error.detail };
    }
    throw error;
  }
}

function plural(value: number, one: string, many: string): string {
  return `${count.format(value)} ${value === 1 ? one : many}`;
}

/** A count the view could not compute is `null`: it reads "unknown", never zero. */
function known(value: number | null): string {
  return value === null ? "unknown" : count.format(value);
}

function ofTotal(part: number | null, whole: number | null): string {
  return part === null || whole === null
    ? "unknown"
    : `${count.format(part)} of ${count.format(whole)}`;
}

function day(value: string | null): string {
  return value === null ? "date unknown" : value.slice(0, 10);
}

function Quote({ span, label }: { span: AtlasSourceSpan; label: string }) {
  return (
    <blockquote className="border-l-2 border-teal-700 bg-white px-3 py-2 font-serif text-[15px] leading-6 text-stone-900">
      <span className="sr-only">{label}: </span>
      {span.text}
    </blockquote>
  );
}

function Timing({ origin }: { origin: LineageOriginRow }) {
  if (origin.countsAsOrigin) {
    return (
      <span className="rounded-sm bg-[#e8efea] px-2 py-0.5 font-medium text-teal-900">
        Said before the amendments
      </span>
    );
  }
  if (origin.isCitation) {
    return (
      <span className="rounded-sm bg-stone-200 px-2 py-0.5 text-stone-700">
        Citation, not a request
      </span>
    );
  }
  if (origin.precedes === null) {
    return (
      <span className="rounded-sm bg-stone-100 px-2 py-0.5 text-stone-600">Order unknown</span>
    );
  }
  return (
    <span className="rounded-sm bg-amber-50 px-2 py-0.5 text-amber-900">
      Said after the first amendment
    </span>
  );
}

function Arrow() {
  return (
    <span
      aria-hidden="true"
      className="hidden text-lg text-stone-400 lg:absolute lg:top-4 lg:-right-3 lg:z-10 lg:block lg:rounded-full lg:bg-white lg:px-1"
    >
      →
    </span>
  );
}

function OriginKind({ origin }: { origin: LineageOriginRow }) {
  return origin.kind === "semantic" ? (
    <span className="rounded-sm bg-violet-50 px-2 py-0.5 text-violet-900">
      Reworded · judged by Jev, unconfirmed
    </span>
  ) : null;
}

/**
 * One link in the brief's order, left to right: what the submission asked, the amendment
 * that carried it, and the wording of the final act (or, for tabled wording, its absence).
 */
export function PhraseCard({ phrase }: { phrase: LineagePhraseRow }) {
  return (
    <li className="rounded-sm border border-stone-200 bg-white">
      <article aria-label={`Phrase ${phrase.phraseId}`} className="grid gap-0 lg:grid-cols-3">
        <section className="relative space-y-3 border-b border-stone-200 p-4 lg:border-r lg:border-b-0">
          <h4 className={eyebrow}>
            {phrase.origins.length === 0
              ? "No submission says it"
              : plural(phrase.origins.length, "submission says it", "submissions say it")}
          </h4>
          <ul className="space-y-3">
            {phrase.origins.map((origin) => (
              <li key={`${origin.documentId}:${origin.kind}`} className="space-y-1.5 text-sm">
                <p className="font-medium text-stone-900">
                  {origin.organisation ?? "Unnamed submitter"}
                </p>
                <p className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-stone-500">
                    {day(origin.publishedAt)} · {origin.documentId}
                  </span>
                  <Timing origin={origin} />
                  <OriginKind origin={origin} />
                </p>
                <Quote span={origin.quote} label="Submission wording" />
              </li>
            ))}
          </ul>
          <Arrow />
        </section>
        <section className="relative space-y-2 border-b border-stone-200 p-4 lg:border-r lg:border-b-0">
          <h4 className={eyebrow}>
            {plural(phrase.amendments.length, "amendment carries it", "amendments carry it")}
          </h4>
          <ul className="space-y-2 text-sm text-stone-700">
            {phrase.amendments.slice(0, AMENDMENTS_PER_CARD).map((amendment) => (
              <li key={amendment.amendmentId}>
                <span className="block font-mono text-xs text-stone-800">
                  {amendment.amendmentId}
                </span>
                {amendment.stage !== null && (
                  <span className="block text-xs text-stone-500">
                    {amendment.stage}
                    {amendment.committee === null ? "" : ` · ${amendment.committee}`} · tabled{" "}
                    {day(amendment.tabledOn)}
                    {amendment.adoptedWords !== null && amendment.newWords !== null
                      ? ` · ${count.format(amendment.adoptedWords)} of ${count.format(amendment.newWords)} words in the final act`
                      : ""}
                  </span>
                )}
                {amendment.authors.length > 0 && (
                  <span className="block text-xs text-stone-600">
                    {amendment.authors.join(", ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
          {phrase.amendments.length > AMENDMENTS_PER_CARD && (
            <p className="text-xs text-stone-500">
              and {count.format(phrase.amendments.length - AMENDMENTS_PER_CARD)} more amendments
              with the same wording
            </p>
          )}
          <Arrow />
        </section>
        <section className="space-y-2 p-4">
          <h4 className={eyebrow}>{phrase.adopted ? "In the final act" : "Tabled, not adopted"}</h4>
          {phrase.finalQuotes.length > 0 ? (
            phrase.finalQuotes.map((span) => (
              <Quote
                key={`${span.record_id}:${span.start}`}
                span={span}
                label="Final act wording"
              />
            ))
          ) : (
            <p className="font-serif text-[15px] leading-6 text-stone-900">{phrase.text}</p>
          )}
          <p className="text-xs text-stone-500">
            {plural(phrase.words, "word", "words")} · {phrase.kind}
            {phrase.joint ? " · joint: credited to several holders" : ""}
          </p>
        </section>
      </article>
    </li>
  );
}

type PhraseTab = "adopted" | "tabled";

const evidenceChoices: readonly { value: PhraseFilter["evidence"]; label: string }[] = [
  { value: "", label: "Any evidence" },
  { value: "first", label: "A submission said it first" },
  { value: "any-origin", label: "Any submission says it" },
  { value: "reworded", label: "Reworded match (Jev)" },
];

const fieldStyle =
  "rounded-sm border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 focus-visible:outline-2 focus-visible:outline-teal-700";

function Phrases({ lineage }: { lineage: PreparedLineage }) {
  const [tab, setTab] = useState<PhraseTab>("adopted");
  const [filter, setFilter] = useState<PhraseFilter>(anyPhrase);
  const [shown, setShown] = useState(PHRASES_PER_PAGE);
  const all = tab === "adopted" ? lineage.adopted : lineage.tabled;
  const facets = useMemo(
    () => phraseFacets([...lineage.adopted, ...lineage.tabled]),
    [lineage.adopted, lineage.tabled],
  );
  const phrases = useMemo(() => filterPhrases(all, filter), [all, filter]);
  function choose(next: PhraseTab) {
    setTab(next);
    setShown(PHRASES_PER_PAGE);
  }
  function update(next: Partial<PhraseFilter>) {
    setFilter((current) => ({ ...current, ...next }));
    setShown(PHRASES_PER_PAGE);
  }
  const filtered =
    filter.query !== "" || filter.group !== "" || filter.committee !== "" || filter.evidence !== "";
  const tabStyle = (active: boolean) =>
    `rounded-sm px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-teal-700 ${active ? "bg-teal-900 text-white" : "bg-white text-stone-700 hover:bg-stone-100"}`;
  return (
    <section aria-labelledby="lineage-evidence" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id="lineage-evidence" className="font-serif text-xl text-stone-900">
          The evidence: submission → amendment → final act
        </h3>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-pressed={tab === "adopted"}
            onClick={() => choose("adopted")}
            className={tabStyle(tab === "adopted")}
          >
            Adopted ({count.format(lineage.adopted.length)})
          </button>
          <button
            type="button"
            aria-pressed={tab === "tabled"}
            onClick={() => choose("tabled")}
            className={tabStyle(tab === "tabled")}
          >
            Tabled, not adopted ({count.format(lineage.tabled.length)})
          </button>
        </div>
      </div>
      <p className="max-w-3xl text-sm leading-6 text-stone-600">
        {tab === "adopted"
          ? "Each phrase stands in the final act, was not in the Commission's proposal, and was inserted by the amendments listed. Submissions that contain the same words, or that Jev judged to ask for it in other words, are shown with their dates."
          : "Wording that amendments inserted and a submission also says, but that did not reach the final act."}
      </p>
      <search className="flex flex-wrap items-end gap-3 rounded-sm border border-stone-200 bg-white p-3">
        <label className="flex min-w-64 flex-1 flex-col gap-1 text-xs text-stone-600">
          Search words, organisations, Members or amendments
          <input
            type="search"
            value={filter.query}
            onChange={(event) => update({ query: event.target.value })}
            placeholder="e.g. biometric, DIGITALEUROPE, sandbox"
            className={fieldStyle}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-stone-600">
          Evidence
          <select
            value={filter.evidence}
            onChange={(event) =>
              update({
                evidence:
                  evidenceChoices.find((choice) => choice.value === event.target.value)?.value ??
                  "",
              })
            }
            className={fieldStyle}
          >
            {evidenceChoices.map((choice) => (
              <option key={choice.value} value={choice.value}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-stone-600">
          Political group
          <select
            value={filter.group}
            onChange={(event) => update({ group: event.target.value })}
            className={fieldStyle}
          >
            <option value="">Any group</option>
            {facets.groups.map((group) => (
              <option key={group} value={group}>
                {group}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-stone-600">
          Committee
          <select
            value={filter.committee}
            onChange={(event) => update({ committee: event.target.value })}
            className={fieldStyle}
          >
            <option value="">Any committee</option>
            {facets.committees.map((committee) => (
              <option key={committee} value={committee}>
                {committee}
              </option>
            ))}
          </select>
        </label>
        {filtered && (
          <button type="button" onClick={() => update(anyPhrase)} className={retryStyle}>
            Clear filters
          </button>
        )}
      </search>
      <p role="status" className="text-xs text-stone-500">
        {count.format(phrases.length)} of {count.format(all.length)} phrases shown, strongest
        evidence first
      </p>
      {phrases.length === 0 ? (
        <p className="text-sm text-stone-600">No phrase matches this selection.</p>
      ) : (
        <ol className="space-y-3">
          {phrases.slice(0, shown).map((phrase) => (
            <PhraseCard key={phrase.phraseId} phrase={phrase} />
          ))}
        </ol>
      )}
      {phrases.length > shown && (
        <button
          type="button"
          onClick={() => setShown((value) => value + PHRASES_PER_PAGE)}
          className={retryStyle}
        >
          Show more ({count.format(phrases.length - shown)} left)
        </button>
      )}
    </section>
  );
}

function CreditList({ title, rows }: { title: string; rows: readonly LineageCreditRow[] }) {
  const [all, setAll] = useState(false);
  if (rows.length === 0) {
    return null;
  }
  const shown = all ? rows : rows.slice(0, CREDITS_SHOWN);
  return (
    <div className="space-y-2">
      <h4 className="text-[11px] font-semibold uppercase tracking-[0.13em] text-stone-600">
        {title}
      </h4>
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-stone-500">
          <tr>
            <th scope="col" className="py-1 font-normal">
              Name
            </th>
            <th scope="col" className="py-1 text-right font-normal">
              Amendments adopted
            </th>
            <th scope="col" className="py-1 text-right font-normal">
              Rate
            </th>
            <th scope="col" className="py-1 text-right font-normal">
              Phrases (joint)
            </th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {shown.map((row) => (
            <tr key={`${row.kind}:${row.holderId}`} className="border-t border-stone-100">
              <td className="py-1.5 pr-3 text-stone-900">{row.name}</td>
              <td className="py-1.5 text-right">
                {count.format(row.amendments)} of {count.format(row.amendmentsTabled)}
              </td>
              <td className="py-1.5 text-right">
                {percent.format(row.amendments / row.amendmentsTabled)}
              </td>
              <td className="py-1.5 text-right">
                {count.format(row.phrases)} ({count.format(row.jointPhrases)})
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > CREDITS_SHOWN && (
        <button type="button" onClick={() => setAll((value) => !value)} className={retryStyle}>
          {all ? "Show fewer" : `Show all ${count.format(rows.length)}`}
        </button>
      )}
    </div>
  );
}

function Credits({ tables }: { tables: readonly LineageCreditTable[] }) {
  return (
    <section aria-labelledby="lineage-credits" className="space-y-4">
      <h3 id="lineage-credits" className="font-serif text-xl text-stone-900">
        Who gets their way: Members and political groups
      </h3>
      <p className="max-w-3xl text-sm leading-6 text-stone-600">
        Every holder of an adopted phrase is credited with the whole phrase; a phrase with several
        holders is joint. Holders are ranked by the share of their amendments on this law that
        reached the final act ("N of M"), not by phrase counts.
      </p>
      {tables.length === 0 ? (
        <p className="text-sm text-stone-600">No adopted wording, so no credit.</p>
      ) : (
        tables.map((table) => (
          <div key={table.basis} className="grid gap-6 lg:grid-cols-2">
            <CreditList title={`Political groups (${table.basis})`} rows={table.groups} />
            <CreditList
              title={`Members and committee text (${table.basis})`}
              rows={table.holders}
            />
          </div>
        ))
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-sm border border-stone-200 bg-white px-4 py-3">
      <dt className="text-xs text-stone-500">{label}</dt>
      <dd className="mt-1 text-2xl tabular-nums text-stone-900">{value}</dd>
    </div>
  );
}

type Prepared =
  | {
      ok: true;
      lineage: PreparedLineage;
      organisations: OrganisationRanking;
      channels: LineageChannels;
      pool: readonly LineagePhraseRow[];
    }
  | { ok: false; error: string };

function LawLineageView({ view, onRetry }: { view: LineageView; onRetry: () => void }) {
  const prepared = useMemo<Prepared>(() => {
    try {
      const lineage = prepareLineage(view);
      return {
        ok: true,
        lineage,
        organisations: rankOrganisations(view),
        channels: lineageChannels(view),
        pool: linkPool(lineage.adopted),
      };
    } catch (error: unknown) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  }, [view]);
  if (!prepared.ok) {
    return (
      <StateMessage announce="alert" title={`The lineage data for ${view.title} is invalid`}>
        <p>
          Nothing from this run is shown, because partial or repaired evidence could mislead. The
          explorer rejected the data with this message:
        </p>
        <p className="font-mono text-xs text-red-800">{prepared.error}</p>
        <p>Rebuild the law with the pipeline, then reload it.</p>
        <button type="button" onClick={onRetry} className={retryStyle}>
          Reload law
        </button>
      </StateMessage>
    );
  }
  const { lineage, organisations, channels, pool } = prepared;
  const { counts } = view;
  const gaps = view.coverage.flatMap((row) => {
    const note = coverageNote(row);
    return note === null ? [] : [note];
  });
  const sections = [
    ["#lineage-questions", "Five questions"],
    ["#lineage-who", "Who"],
    ["#lineage-how", "How"],
    ["#lineage-check", "Check 3 links"],
    ["#lineage-evidence", "Evidence"],
    ["#lineage-limits", "Limits"],
  ] as const;
  return (
    <main className="mx-auto max-w-[1536px] space-y-8 px-5 py-6 sm:px-8">
      <header className="space-y-1">
        <h2 className="font-serif text-2xl text-stone-900">{view.title}</h2>
        <p className="text-xs text-stone-500">
          {view.procedure_id} · {view.method} ({view.method_revision}) · run {view.run_id},
          generated {view.generated_at}
        </p>
      </header>
      <nav
        aria-label="Sections of this law"
        className="sticky top-0 z-20 -mx-5 flex flex-wrap gap-1 border-b border-stone-200 bg-stone-50/95 px-5 py-2 backdrop-blur sm:-mx-8 sm:px-8"
      >
        {sections.map(([href, label]) => (
          <a
            key={href}
            href={href}
            className="rounded-sm px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-200 focus-visible:outline-2 focus-visible:outline-teal-700"
          >
            {label}
          </a>
        ))}
      </nav>
      {view.status === "unknown" && (
        <p role="alert" className="max-w-3xl text-sm leading-6 text-amber-900">
          Adoption could not be computed for this law.{" "}
          {sentence(view.reason ?? "No reason was recorded")} Nothing is adopted or credited, and
          counts that could not be computed read "unknown".
        </p>
      )}
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Adopted phrases" value={known(counts.adopted_phrases)} />
        <Stat
          label="Amendments with adopted wording"
          value={ofTotal(counts.amendments_adopting, counts.amendments)}
        />
        <Stat
          label="New final-act words traced to an amendment"
          value={ofTotal(counts.linked_units, counts.changed_units)}
        />
        <Stat
          label="Consultation documents that said it first"
          value={ofTotal(counts.documents_with_origin, counts.documents_read)}
        />
      </dl>
      <FiveQuestions questions={questionsFor(view, lineage, organisations, channels)} />
      <WhoShaped ranking={organisations} />
      <Credits tables={lineage.credits} />
      <Channels channels={channels} />
      <LinkCheck
        pool={pool}
        renderLink={(phrase) => <PhraseCard key={phrase.phraseId} phrase={phrase} />}
      />
      <Phrases lineage={lineage} />
      <details
        id="lineage-limits"
        className="rounded-sm border border-stone-200 bg-white p-4 text-sm leading-6 text-stone-600"
      >
        <summary className="cursor-pointer font-medium text-stone-900">
          Limitations and source coverage
        </summary>
        <ul className="mt-3 list-disc space-y-1 pl-5">
          {view.limitations.map((limitation) => (
            <li key={limitation}>{sentence(limitation)}</li>
          ))}
          {gaps.length === 0 ? (
            <li>Every source layer recorded for this law is complete.</li>
          ) : (
            gaps.map((gap) => <li key={gap}>{gap}</li>)
          )}
        </ul>
      </details>
    </main>
  );
}

function LawContent({ slug, law }: { slug: string; law: LineageLawSummary | null }) {
  const result = useResource(lineageViewUrl(slug), readLawView);
  const name = law === null ? slug : law.title;
  if (result.error !== null) {
    return (
      <StateMessage announce="alert" title={`The lineage of ${name} could not be loaded`}>
        <p>{result.error}</p>
        <p>Check that the backend is running (make dev-backend), then retry.</p>
        <button type="button" onClick={result.retry} className={retryStyle}>
          Retry law
        </button>
      </StateMessage>
    );
  }
  if (result.data === null) {
    return (
      <StateMessage announce="status" title={`Loading the lineage of ${name}…`}>
        <p>Reading the law's adopted wording, amendments and submissions from the backend.</p>
      </StateMessage>
    );
  }
  if (!result.data.found) {
    return (
      <StateMessage announce="alert" title={`No lineage view for ${name}`}>
        <p>{result.data.detail}</p>
        <p>
          Build it from the repository root with its procedure reference, for example{" "}
          <code className="font-mono text-xs text-stone-800">{buildCommand}</code>, then reload this
          page.
        </p>
      </StateMessage>
    );
  }
  return <LawLineageView view={result.data.view} onRetry={result.retry} />;
}

/**
 * Lists the laws with a lineage view and opens the one named by `?law=`, so a reload or a
 * shared link reopens it. Selection uses the history API, which Next.js syncs with
 * `useSearchParams`, so back and forward move between laws without a page load.
 */
export function LineageLawBrowser() {
  const searchParams = useSearchParams();
  const selected = searchParams.get("law") || null;
  const laws = useResource(lineageLawsUrl, readLineageLaws);
  const collected = laws.data?.laws ?? null;
  function select(slug: string) {
    if (slug === selected) {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    params.set("law", slug);
    window.history.pushState(null, "", `?${params.toString()}`);
  }
  const navStyle =
    "rounded-sm px-3 py-2 text-xs font-medium text-stone-500 hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700";
  return (
    <div className="min-h-dvh bg-stone-50 text-stone-900">
      <header className="flex h-[76px] items-center justify-between gap-4 border-b border-stone-200 bg-white px-5 sm:px-8">
        <div className="flex items-center gap-4">
          <span className="text-xl font-semibold tracking-tight text-stone-900">Influence</span>
          <span className="hidden h-5 w-px bg-stone-300 sm:block" />
          <span className="hidden text-sm text-stone-500 sm:block">Lineage explorer</span>
        </div>
        <nav aria-label="Other views" className="flex gap-1">
          <Link href="/" className={navStyle}>
            Evidence workspace
          </Link>
        </nav>
      </header>
      <nav
        aria-label="Collected laws"
        className="border-b border-stone-200 bg-white px-5 py-5 sm:px-8"
      >
        <div className="mx-auto max-w-[1536px]">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.13em] text-stone-600">
            Collected laws
          </h2>
          {laws.loading && (
            <p role="status" className="mt-3 text-sm text-stone-500">
              Loading collected laws…
            </p>
          )}
          {laws.error !== null && (
            <div role="alert" className="mt-3 space-y-2 text-sm leading-6 text-stone-600">
              <p>The list of collected laws could not be loaded. {laws.error}</p>
              <p>Check that the backend is running (make dev-backend), then retry.</p>
              <button type="button" onClick={laws.retry} className={retryStyle}>
                Retry laws
              </button>
            </div>
          )}
          {collected?.length === 0 && (
            <p className="mt-3 max-w-3xl text-sm leading-6 text-stone-600">
              No law has a lineage view yet. Build one from the repository root, for example{" "}
              <code className="font-mono text-xs text-stone-800">{buildCommand}</code>, then reload
              this page.
            </p>
          )}
          {collected !== null && collected.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-2">
              {collected.map((law) => (
                <li key={law.slug}>
                  <button
                    type="button"
                    aria-pressed={law.slug === selected}
                    onClick={() => select(law.slug)}
                    className={`rounded-sm border px-4 py-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 ${law.slug === selected ? "border-teal-800 bg-[#e8efea]" : "border-stone-300 bg-white hover:bg-stone-100"}`}
                  >
                    <span className="block text-sm font-medium text-stone-900">{law.title}</span>
                    <span className="mt-1 block text-xs tabular-nums text-stone-500">
                      {law.procedure_id} ·{" "}
                      {law.adopted_phrases === null
                        ? "adoption unknown"
                        : plural(law.adopted_phrases, "adopted phrase", "adopted phrases")}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </nav>
      {selected === null ? (
        collected !== null &&
        collected.length > 0 && (
          <StateMessage announce={null} title="Choose a law">
            <p>
              Open a collected law to see which of its final wording came from which amendments, who
              tabled them, and which submissions said it first.
            </p>
          </StateMessage>
        )
      ) : (
        <LawContent
          key={selected}
          slug={selected}
          law={collected?.find((law) => law.slug === selected) ?? null}
        />
      )}
    </div>
  );
}
