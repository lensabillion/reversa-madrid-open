"use client";

import { useState } from "react";
import type { AmendmentDetail, AmendmentPage, DatasetOverview } from "../lib/api";
import { useResource } from "../lib/use-resource";
import { CompareTexts } from "./compare-texts";
import { EvidenceColumns } from "./evidence-columns";
import { InfluenceNetwork } from "./influence-network";

const buttonStyle =
  "rounded-sm px-3 py-2 text-xs font-medium transition-colors hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:cursor-not-allowed disabled:opacity-35";

function Evidence({ detail }: { detail: AmendmentDetail }) {
  const [sourceId, setSourceId] = useState<string | null>(null);
  const source = detail.sources.find((item) => item.candidate_id === sourceId) ?? detail.sources[0];
  if (!source) {
    return (
      <div className="py-7">
        <p className="mb-8 text-sm text-stone-500">
          No source candidates recorded for this amendment.
        </p>
        <EvidenceColumns amendment={detail.text} submission={null} evidence={[]} mode="edits" />
      </div>
    );
  }
  return (
    <section aria-label="Source evidence" className="pt-6">
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div className="min-w-0 flex-1">
          <label
            htmlFor="source"
            className="mb-2 block text-[11px] font-medium uppercase tracking-[0.14em] text-stone-500"
          >
            Source · {detail.total_sources} candidates
          </label>
          <select
            id="source"
            value={source.candidate_id}
            onChange={(event) => setSourceId(event.target.value)}
            className="max-w-full border-b border-stone-300 bg-transparent py-2 pr-8 text-lg font-medium text-stone-900 focus-visible:outline-2 focus-visible:outline-teal-700"
          >
            {detail.sources.map((item) => (
              <option key={item.candidate_id} value={item.candidate_id}>
                {item.organization} · p. {item.page}
                {item.historically_verified ? " · verified" : ""}
              </option>
            ))}
          </select>
          <p className="mt-2 break-all text-xs leading-5 text-stone-500">
            {source.document} · p. {source.page}
          </p>
          {detail.sources.length < detail.total_sources && (
            <p className="mt-1 text-xs text-stone-500">
              Showing {detail.sources.length} of {detail.total_sources}; verified first.
            </p>
          )}
        </div>
        <div className="flex items-start gap-7 pt-1">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-stone-500">
              LobbyPlag review
            </p>
            <p
              className={`mt-2 text-sm font-medium ${source.historically_verified ? "text-teal-800" : "text-stone-600"}`}
            >
              {source.historically_verified ? "Verified" : "Unverified"}
            </p>
          </div>
          <div className="min-w-20 text-right">
            <p className="text-[10px] font-medium uppercase tracking-wider text-stone-500">
              Lexical similarity
            </p>
            <p className="mt-1 font-mono text-xl tracking-tight text-stone-700">
              {source.score ? source.score.score.toFixed(2) : "—"}
            </p>
          </div>
        </div>
      </div>
      <EvidenceColumns
        key={source.candidate_id}
        amendment={detail.text}
        submission={source.text}
        evidence={source.score?.evidence ?? []}
        mode="edits"
      />
      {source.score?.negation_conflict && (
        <p role="note" className="border-l-2 border-amber-500 pl-3 text-sm text-amber-900">
          Negation differs between these edits.
        </p>
      )}
      {source.score_unavailable_reason && (
        <p className="text-sm text-stone-500">{source.score_unavailable_reason}</p>
      )}
      <details className="mt-7 border-t border-stone-200 pt-4 text-xs leading-5 text-stone-500">
        <summary className="w-fit cursor-pointer font-medium text-stone-600">
          About this evidence
        </summary>
        <p className="mt-3 max-w-2xl">{detail.coverage_note}</p>
        {source.score && (
          <p className="mt-2 max-w-2xl">
            Similarity measures shared edits, not the probability of influence. Paraphrases may be
            missed.
          </p>
        )}
      </details>
    </section>
  );
}

/** One evidence workspace keeps selection and network context together. */
export default function EvidenceWorkspace() {
  const [mode, setMode] = useState<"explore" | "compare">("explore");
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [offset, setOffset] = useState(0);
  const [verifiedOnly, setVerifiedOnly] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<"evidence" | "network">("evidence");
  const overview = useResource<DatasetOverview>(mode === "explore" ? "/api/v1/demo" : null);
  const list = useResource<AmendmentPage>(
    mode === "explore"
      ? `/api/v1/amendments?q=${encodeURIComponent(query)}&offset=${offset}&limit=12&verified_only=${verifiedOnly}`
      : null,
  );
  const selected = list.data?.items.find((item) => item.id === selectedId) ?? list.data?.items[0];
  const detail = useResource<AmendmentDetail>(
    selected ? `/api/v1/amendments/${encodeURIComponent(selected.id)}` : null,
  );
  return (
    <div className="min-h-dvh">
      <a
        href={mode === "compare" ? "#comparison" : "#evidence"}
        className="sr-only z-50 bg-white p-3 focus:not-sr-only focus:fixed"
      >
        Skip to evidence
      </a>
      <header className="flex h-[76px] items-center justify-between gap-4 border-b border-stone-200 px-5 sm:px-8">
        <div className="flex items-center gap-4">
          <span className="text-xl font-semibold tracking-tight text-stone-900">Influence</span>
          <span className="hidden h-5 w-px bg-stone-300 sm:block" />
          <span className="hidden text-sm text-stone-500 sm:block">Evidence workspace</span>
        </div>
        <nav aria-label="Workspace" className="flex gap-1">
          <button
            type="button"
            aria-pressed={mode === "explore"}
            onClick={() => setMode("explore")}
            className={`${buttonStyle} ${mode === "explore" ? "bg-stone-100 text-teal-900" : "text-stone-500"}`}
          >
            Explore
          </button>
          <button
            type="button"
            aria-pressed={mode === "compare"}
            onClick={() => setMode("compare")}
            className={`${buttonStyle} ${mode === "compare" ? "bg-stone-100 text-teal-900" : "text-stone-500"}`}
          >
            Compare texts
          </button>
        </nav>
      </header>
      <div hidden={mode !== "compare"}>
        <CompareTexts />
      </div>
      {mode === "explore" && (
        <>
          <div className="border-b border-stone-200 px-5 py-7 sm:px-8">
            <div className="mx-auto flex max-w-[1540px] flex-wrap items-end justify-between gap-4">
              <div>
                <p className="mb-2 text-[10px] font-medium uppercase tracking-[0.2em] text-teal-800">
                  2012/0011(COD)
                </p>
                <h1 className="font-serif text-3xl tracking-tight text-stone-900 sm:text-4xl">
                  GDPR amendments
                </h1>
              </div>
              {overview.data && (
                <p className="text-xs tabular-nums text-stone-500">
                  <span className="font-medium text-stone-800">
                    {overview.data.amendments.toLocaleString("en")}
                  </span>{" "}
                  amendments <span className="mx-2 text-stone-300">/</span>{" "}
                  <span className="font-medium text-stone-800">{overview.data.verified_links}</span>{" "}
                  verified links
                </p>
              )}
              {overview.error && (
                <p role="alert" className="text-xs text-stone-500">
                  {overview.error}{" "}
                  <button type="button" onClick={overview.retry} className="ml-2 underline">
                    Retry overview
                  </button>
                </p>
              )}
            </div>
          </div>
          <div className="mx-auto grid max-w-[1604px] md:min-h-[calc(100dvh-192px)] md:grid-cols-[280px_minmax(0,1fr)] lg:grid-cols-[310px_minmax(0,1fr)]">
            <aside
              aria-label="Amendment browser"
              className="border-b border-stone-200 bg-[#f7f6f2] px-5 py-6 md:border-r md:border-b-0 sm:px-8"
            >
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  setQuery(draft);
                  setOffset(0);
                  setSelectedId(null);
                }}
              >
                <label
                  htmlFor="amendment-search"
                  className="mb-3 block text-[11px] font-semibold uppercase tracking-[0.13em] text-stone-600"
                >
                  Amendments
                </label>
                <div className="flex rounded-sm border border-stone-300 bg-white focus-within:border-teal-700">
                  <input
                    id="amendment-search"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    maxLength={200}
                    placeholder="Committee, number or author"
                    className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-xs outline-none"
                  />
                  <button
                    type="submit"
                    aria-label="Search amendments"
                    className="px-3 text-stone-500 hover:text-teal-800 focus-visible:outline-2 focus-visible:outline-teal-700"
                  >
                    ↵
                  </button>
                </div>
              </form>
              <label className="my-4 flex items-center gap-2 text-xs text-stone-600">
                <input
                  type="checkbox"
                  checked={verifiedOnly}
                  onChange={(event) => {
                    setVerifiedOnly(event.target.checked);
                    setOffset(0);
                    setSelectedId(null);
                  }}
                  className="h-3.5 w-3.5 accent-teal-800"
                />
                Verified links only
              </label>
              {list.loading && (
                <p role="status" className="py-8 text-sm text-stone-500">
                  Loading amendments…
                </p>
              )}
              {list.error && (
                <div role="alert" className="py-6 text-sm leading-6 text-stone-600">
                  <p>{list.error}</p>
                  <button
                    type="button"
                    onClick={list.retry}
                    className="mt-3 text-teal-800 underline underline-offset-4"
                  >
                    Retry amendments
                  </button>
                </div>
              )}
              {list.data && (
                <>
                  <p className="mb-3 text-[10px] tabular-nums text-stone-400">
                    {list.data.total.toLocaleString("en")}{" "}
                    {list.data.total === 1 ? "result" : "results"}
                  </p>
                  <div className="max-h-[300px] overflow-y-auto md:max-h-none">
                    {list.data.items.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        aria-pressed={selected?.id === item.id}
                        onClick={() => {
                          setSelectedId(item.id);
                        }}
                        className={`mb-1 block w-full rounded-sm border-l-2 px-3 py-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-teal-700 ${selected?.id === item.id ? "border-teal-800 bg-[#e8efea]" : "border-transparent hover:bg-stone-100"}`}
                      >
                        <span className="flex items-baseline justify-between gap-2">
                          <span className="font-mono text-sm font-medium uppercase text-stone-800">
                            {item.committee} {item.number}
                          </span>
                          {item.verified_links > 0 && (
                            <span className="text-[10px] text-teal-800">
                              {item.verified_links} verified
                            </span>
                          )}
                        </span>
                        <span className="mt-1.5 block truncate text-xs text-stone-500">
                          {item.authors.join(", ") || "No named author"}
                        </span>
                      </button>
                    ))}
                  </div>
                  {list.data.total === 0 && (
                    <p className="py-8 text-sm text-stone-500">No amendments found.</p>
                  )}
                  <nav
                    aria-label="Amendment pages"
                    className="mt-5 flex items-center justify-between border-t border-stone-200 pt-3"
                  >
                    <button
                      type="button"
                      disabled={offset === 0}
                      onClick={() => {
                        setOffset(Math.max(0, offset - 12));
                        setSelectedId(null);
                      }}
                      className={buttonStyle}
                    >
                      ← Previous
                    </button>
                    <button
                      type="button"
                      disabled={offset + 12 >= list.data.total}
                      onClick={() => {
                        setOffset(offset + 12);
                        setSelectedId(null);
                      }}
                      className={buttonStyle}
                    >
                      Next →
                    </button>
                  </nav>
                </>
              )}
            </aside>
            <main id="evidence" className="min-w-0 px-5 py-7 sm:px-8 lg:px-12">
              {detail.loading && (
                <p role="status" className="py-14 text-sm text-stone-500">
                  Loading evidence…
                </p>
              )}
              {detail.error && (
                <div role="alert" className="py-12 text-sm text-stone-600">
                  <p>{detail.error}</p>
                  <button
                    type="button"
                    onClick={detail.retry}
                    className="mt-4 text-teal-800 underline underline-offset-4"
                  >
                    Retry evidence
                  </button>
                </div>
              )}
              {!selected && !list.loading && !list.error && (
                <p className="py-14 text-sm text-stone-500">
                  Select an amendment to inspect its sources.
                </p>
              )}
              {detail.data && (
                <>
                  <div className="mb-7">
                    <p className="mb-2 text-[10px] font-medium uppercase tracking-[0.14em] text-stone-500">
                      Amendment ·{" "}
                      {detail.data.amendment.relations.join(" · ") || "Location unspecified"}
                    </p>
                    <h2 className="font-serif text-3xl text-stone-900">
                      {detail.data.amendment.committee.toUpperCase()} {detail.data.amendment.number}
                    </h2>
                    <p className="mt-3 text-sm leading-6 text-stone-500">
                      {[...new Set(detail.data.amendment.authors)].join(" · ") || "No named author"}
                    </p>
                  </div>
                  <div className="flex gap-7 border-b border-stone-200">
                    <button
                      type="button"
                      aria-pressed={view === "evidence"}
                      onClick={() => setView("evidence")}
                      className={`border-b-2 pb-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-teal-700 ${view === "evidence" ? "border-teal-800 text-teal-900" : "border-transparent text-stone-500"}`}
                    >
                      Evidence
                    </button>
                    <button
                      type="button"
                      aria-pressed={view === "network"}
                      onClick={() => setView("network")}
                      className={`border-b-2 pb-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-teal-700 ${view === "network" ? "border-teal-800 text-teal-900" : "border-transparent text-stone-500"}`}
                    >
                      Network
                    </button>
                  </div>
                  {view === "evidence" ? (
                    <Evidence key={detail.data.amendment.id} detail={detail.data} />
                  ) : (
                    <InfluenceNetwork
                      key={detail.data.amendment.id}
                      amendmentId={detail.data.amendment.id}
                    />
                  )}
                </>
              )}
            </main>
          </div>
        </>
      )}
    </div>
  );
}
