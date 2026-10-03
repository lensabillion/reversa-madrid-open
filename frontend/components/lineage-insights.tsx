"use client";

import { useMemo, useState } from "react";
import type { LineageCreditTable, LineagePhraseRow, PreparedLineage } from "../lib/lineage";
import type { LineageView } from "../lib/lineage-api";
import {
  type ChannelCount,
  drawLinks,
  type LineageChannels,
  type OrganisationRanking,
  type OrganisationRow,
} from "../lib/lineage-insights";
import { retryStyle } from "./atlas-law-browser";
import { KindBadge, KindLegend, KindSplitBar } from "./lineage-kind";
import type { LawTab } from "./lineage-law-browser";

const count = new Intl.NumberFormat("en-US");
const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });
const ORGANISATIONS_SHOWN = 10;
/** The brief's check: the jury picks three links at random and reads both texts side by side. */
export const LINKS_DRAWN = 3;

const eyebrow = "text-[11px] font-semibold uppercase tracking-[0.13em] text-stone-600";

function share(part: number, whole: number): string {
  return whole === 0 ? "–" : percent.format(part / whole);
}

/**
 * A single-series magnitude bar in neutral gray (teal and violet mean the analysis method), anchored at zero, with the value as text beside it
 * so the number never depends on reading the bar. `title` gives the exact count on hover.
 */
export function Bar({ value, max, label }: { value: number; max: number; label: string }) {
  const width = max === 0 ? 0 : Math.max(2, Math.round((value / max) * 100));
  return (
    <span className="flex items-center gap-2" title={`${label}: ${count.format(value)}`}>
      <span aria-hidden="true" className="h-2 w-24 shrink-0 rounded-sm bg-stone-100">
        <span
          className="block h-2 rounded-r-[4px] bg-stone-500"
          style={{ width: value === 0 ? 0 : `${width}%` }}
        />
      </span>
      <span className="tabular-nums">{count.format(value)}</span>
    </span>
  );
}

type QuestionState = "answered" | "partial" | "missing";

interface Question {
  id: string;
  label: string;
  question: string;
  state: QuestionState;
  answer: string;
  /** The tab that holds the detail, or `null` when nothing on the page does. */
  more: LawTab | null;
}

const stateText: Record<QuestionState, string> = {
  answered: "Answered",
  partial: "Partly",
  missing: "Not yet",
};

const stateStyle: Record<QuestionState, string> = {
  answered: "bg-[#e8efea] text-teal-900",
  partial: "bg-amber-50 text-amber-900",
  missing: "bg-stone-100 text-stone-600",
};

function topGroup(tables: readonly LineageCreditTable[]): string | null {
  const row = tables.find((table) => table.basis === "verbatim")?.groups[0];
  return row === undefined
    ? null
    : `${row.name} (${count.format(row.amendments)} of ${count.format(row.amendmentsTabled)} amendments adopted)`;
}

/** The brief's five questions, each answered in one line from this law's lineage, or not. */
export function questionsFor(
  view: LineageView,
  lineage: PreparedLineage,
  organisations: OrganisationRanking,
  channels: LineageChannels,
): readonly Question[] {
  const leader = organisations.rows.find((row) => row.adoptedFirst > 0);
  const group = topGroup(lineage.credits);
  const committee = channels.byCommittee[0];
  const stage = channels.byStage[0];
  return [
    {
      id: "who",
      label: "Who",
      question: "Who shaped this law the most?",
      state: leader === undefined ? "missing" : "answered",
      answer:
        leader === undefined
          ? "No organisation said adopted wording before the amendments."
          : `${leader.name} leads, with ${plural(leader.adoptedFirst, "adopted phrase")} said first.${group === null ? "" : ` Top group: ${group}.`}`,
      more: "who",
    },
    {
      id: "what",
      label: "What",
      question: "On which topics?",
      state: "partial",
      answer: `${count.format(lineage.adopted.length)} phrases of ${view.title} came from amendments. Search them by topic.`,
      more: "evidence",
    },
    {
      id: "towards",
      label: "Towards",
      question: "Pushing for what?",
      state: "partial",
      answer:
        "Each link puts the request beside the final wording. Direction labels are not computed here.",
      more: "evidence",
    },
    {
      id: "how",
      label: "How",
      question: "Through which channels?",
      state: stage === undefined ? "missing" : "answered",
      answer:
        stage === undefined || committee === undefined
          ? "No adopting amendment to describe."
          : `${share(stage.count, channels.adoptingAmendments)} at the ${stage.label} stage, mostly ${committee.label}; ${share(channels.crossGroup, channels.withGroup)} across groups.`,
      more: "how",
    },
    {
      id: "next",
      label: "Next",
      question: "Who wins next?",
      state: "missing",
      answer: "No forecast yet: it needs several laws and years.",
      more: null,
    },
  ];
}

function plural(value: number, one: string): string {
  return `${count.format(value)} ${value === 1 ? one : `${one}s`}`;
}

export function FiveQuestions({
  questions,
  onOpen,
}: {
  questions: readonly Question[];
  onOpen: (tab: LawTab) => void;
}) {
  return (
    <section aria-labelledby="lineage-questions" className="space-y-3">
      <h3 id="lineage-questions" className="font-serif text-xl text-stone-900">
        The five questions, for this law
      </h3>
      <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {questions.map((item) => (
          <li
            key={item.id}
            className="flex flex-col gap-2 rounded-sm border border-stone-200 bg-white p-4"
          >
            <p className="flex items-center justify-between gap-2">
              <span className={eyebrow}>{item.label}</span>
              <span className={`rounded-sm px-2 py-0.5 text-[11px] ${stateStyle[item.state]}`}>
                {stateText[item.state]}
              </span>
            </p>
            <p className="text-sm font-medium text-stone-900">{item.question}</p>
            <p className="text-sm leading-6 text-stone-700">{item.answer}</p>
            {item.more !== null && (
              <button
                type="button"
                onClick={() => {
                  const tab = item.more;
                  if (tab !== null) {
                    onOpen(tab);
                  }
                }}
                className="mt-auto self-start text-sm font-medium text-teal-800 underline underline-offset-2"
              >
                Explore →
              </button>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

function OrganisationTable({ rows }: { rows: readonly OrganisationRow[] }) {
  const max = rows.reduce((top, row) => Math.max(top, row.adoptedFirst), 0);
  const semantic = rows.some((row) => row.adoptedFirstSemantic > 0 || row.reworded > 0);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="text-xs text-stone-500">
          <tr>
            <th scope="col" className="py-1 font-normal">
              Organisation
            </th>
            <th scope="col" className="py-1 font-normal">
              Adopted, said first
            </th>
            <th scope="col" className="py-1 text-right font-normal">
              Said first, not adopted
            </th>
            {semantic && (
              <th scope="col" className="py-1 text-right font-normal">
                <KindBadge kind="semantic" note="only" />
              </th>
            )}
            <th scope="col" className="py-1 text-right font-normal">
              First said
            </th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {rows.map((row) => (
            <tr key={row.key} className="border-t border-stone-100">
              <td className="py-1.5 pr-3 text-stone-900">{row.name}</td>
              <td className="py-1.5 pr-3">
                <KindSplitBar
                  lexical={row.adoptedFirstLexical}
                  semantic={row.adoptedFirstSemantic}
                  max={max}
                />
              </td>
              <td className="py-1.5 text-right">{count.format(row.tabledOnly)}</td>
              {semantic && <td className="py-1.5 text-right">{count.format(row.reworded)}</td>}
              <td className="py-1.5 text-right text-stone-500">
                {row.firstSaid === null ? "undated" : row.firstSaid.slice(0, 10)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** WHO: organisations from the submissions, beside the Members and groups who tabled. */
export function WhoShaped({ ranking }: { ranking: OrganisationRanking }) {
  const [query, setQuery] = useState("");
  const [all, setAll] = useState(false);
  const matching = useMemo(() => {
    const folded = query.trim().toLowerCase();
    return folded === ""
      ? ranking.rows
      : ranking.rows.filter((row) => row.name.toLowerCase().includes(folded));
  }, [ranking.rows, query]);
  const shown = all ? matching : matching.slice(0, ORGANISATIONS_SHOWN);
  return (
    <section aria-labelledby="lineage-who" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h3 id="lineage-who" className="font-serif text-xl text-stone-900">
            Who gets their way: organisations
          </h3>
          <p className="max-w-3xl text-sm leading-6 text-stone-600">
            Ranked by adopted wording each organisation said before the amendments.
          </p>
          <KindLegend />
        </div>
        <label className="flex flex-col gap-1 text-xs text-stone-600">
          Find an organisation
          <input
            type="search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setAll(false);
            }}
            className="w-64 rounded-sm border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900"
          />
        </label>
      </div>
      {ranking.rows.length === 0 ? (
        <p className="text-sm text-stone-600">
          No named organisation's submission says wording that amendments inserted.
        </p>
      ) : matching.length === 0 ? (
        <p className="text-sm text-stone-600">No organisation matches "{query}".</p>
      ) : (
        <OrganisationTable rows={shown} />
      )}
      <p className="text-xs text-stone-500">
        {count.format(ranking.rows.length)} organisations · {count.format(ranking.unnamedDocuments)}{" "}
        matching documents without an organisation name (citizens or unnamed attachments) ·{" "}
        {count.format(ranking.citations)} matches left out as citations of other acts ·{" "}
        {count.format(ranking.notFirst)} matches dated after the amendment or undated, which cannot
        show influence
      </p>
      {matching.length > ORGANISATIONS_SHOWN && (
        <button type="button" onClick={() => setAll((value) => !value)} className={retryStyle}>
          {all ? "Show fewer" : `Show all ${count.format(matching.length)}`}
        </button>
      )}
    </section>
  );
}

function CountList({
  title,
  rows,
  total,
  limit,
}: {
  title: string;
  rows: readonly ChannelCount[];
  total: number;
  limit: number;
}) {
  const max = rows.reduce((top, row) => Math.max(top, row.count), 0);
  const shown = rows.slice(0, limit);
  const rest = rows.slice(limit).reduce((sum, row) => sum + row.count, 0);
  return (
    <div className="space-y-2 rounded-sm border border-stone-200 bg-white p-4">
      <h4 className={eyebrow}>{title}</h4>
      {rows.length === 0 ? (
        <p className="text-sm text-stone-600">None.</p>
      ) : (
        <table className="w-full text-left text-sm">
          <tbody>
            {shown.map((row) => (
              <tr key={row.label}>
                <th scope="row" className="py-1 pr-3 font-normal text-stone-800">
                  {row.label}
                </th>
                <td className="py-1">
                  <Bar value={row.count} max={max} label={row.label} />
                </td>
                <td className="py-1 text-right text-xs tabular-nums text-stone-500">
                  {share(row.count, total)}
                </td>
              </tr>
            ))}
            {rest > 0 && (
              <tr>
                <th scope="row" className="py-1 pr-3 font-normal text-stone-500">
                  {count.format(rows.length - limit)} others
                </th>
                <td className="py-1 tabular-nums text-stone-600">{count.format(rest)}</td>
                <td className="py-1 text-right text-xs tabular-nums text-stone-500">
                  {share(rest, total)}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-sm border border-stone-200 bg-white px-4 py-3">
      <dt className="text-xs text-stone-500">{label}</dt>
      <dd className="mt-1 text-2xl tabular-nums text-stone-900">{value}</dd>
      <dd className="mt-1 text-xs leading-5 text-stone-500">{note}</dd>
    </div>
  );
}

/** HOW: stage, committee, coalition and timing of the wording that reached the law. */
export function Channels({ channels }: { channels: LineageChannels }) {
  const { timing } = channels;
  return (
    <section aria-labelledby="lineage-how" className="space-y-4">
      <div className="space-y-1">
        <h3 id="lineage-how" className="font-serif text-xl text-stone-900">
          How it got there: channels and timing
        </h3>
        <p className="max-w-3xl text-sm leading-6 text-stone-600">
          Over the {count.format(channels.adoptingAmendments)} amendments whose wording reached the
          final act.
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile
          label="Submission said it before the amendment"
          value={share(timing.askFirst, timing.askFirst + timing.amendmentFirst)}
          note={`${count.format(timing.askFirst)} of ${count.format(timing.askFirst + timing.amendmentFirst)} dated matches; ${count.format(timing.unknownDate)} undated`}
        />
        <Tile
          label="Cross-group coalitions"
          value={share(channels.crossGroup, channels.withGroup)}
          note={`${count.format(channels.crossGroup)} of ${count.format(channels.withGroup)} adopting amendments with a known group were tabled by Members of two or more groups`}
        />
        <div className="rounded-sm border border-stone-200 bg-white px-4 py-3">
          <dt className="text-xs text-stone-500">Matches by method</dt>
          <dd className="mt-2 flex flex-wrap items-center gap-2 text-sm tabular-nums text-stone-900">
            <KindBadge kind="verbatim" note={count.format(channels.verbatimMatches)} />
            <KindBadge kind="semantic" note={count.format(channels.rewordedMatches)} />
          </dd>
          <dd className="mt-1 text-xs leading-5 text-stone-500">
            submission matches found word for word, and reworded ones judged by Jev
          </dd>
        </div>
        <Tile
          label="Citations set aside"
          value={count.format(timing.citation)}
          note="matches that quote another act or the proposal: shared wording, not a request"
        />
      </dl>
      <div className="grid gap-3 lg:grid-cols-3">
        <CountList
          title="Adopting amendments by stage"
          rows={channels.byStage}
          total={channels.adoptingAmendments}
          limit={4}
        />
        <CountList
          title="Adopting amendments by committee"
          rows={channels.byCommittee}
          total={channels.adoptingAmendments}
          limit={6}
        />
        <CountList
          title="Adopting amendments by year tabled"
          rows={channels.byYear}
          total={channels.adoptingAmendments}
          limit={8}
        />
      </div>
    </section>
  );
}

function randomSeed(): number {
  const values = new Uint32Array(1);
  crypto.getRandomValues(values);
  return values[0] ?? 1;
}

/**
 * The jury's check, built in: draw three published links at random and read each one's
 * submission, amendment and final wording side by side. The seed is shown so a draw can be
 * repeated; `renderLink` draws the same card the evidence list uses.
 */
export function LinkCheck({
  pool,
  renderLink,
}: {
  pool: readonly LineagePhraseRow[];
  renderLink: (phrase: LineagePhraseRow) => React.ReactNode;
}) {
  const [seed, setSeed] = useState<number | null>(null);
  const drawn = useMemo(
    () => (seed === null ? [] : drawLinks(pool, LINKS_DRAWN, seed)),
    [pool, seed],
  );
  return (
    <section aria-labelledby="lineage-check" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h3 id="lineage-check" className="font-serif text-xl text-stone-900">
            Check three links at random
          </h3>
          <p className="max-w-3xl text-sm leading-6 text-stone-600">
            Draws {LINKS_DRAWN} of the {count.format(pool.length)} adopted phrases a submission said
            word for word before the amendments: what the organisation asked, the amendment that
            carried it, and the final act, side by side.
          </p>
        </div>
        <button
          type="button"
          disabled={pool.length === 0}
          onClick={() => setSeed(randomSeed())}
          className="rounded-sm bg-teal-900 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:bg-stone-300"
        >
          {seed === null ? `Draw ${LINKS_DRAWN} links` : "Draw again"}
        </button>
      </div>
      {pool.length === 0 && (
        <p className="text-sm text-stone-600">
          No adopted phrase has a submission dated before its amendments, so there is no link to
          draw.
        </p>
      )}
      {seed !== null && (
        <>
          <p className="text-xs text-stone-500">Seed {seed}: the same seed draws the same links.</p>
          <ol className="space-y-3">{drawn.map((phrase) => renderLink(phrase))}</ol>
        </>
      )}
    </section>
  );
}
