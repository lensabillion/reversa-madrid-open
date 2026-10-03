"use client";

import { useState } from "react";
import { AtlasEvidence, type AtlasEvidenceProps } from "./atlas-evidence";

/** A display projection, not the shared pipeline/API schema; the adapter supplies assessed records. */
export interface AtlasLinkView {
  id: string;
  law: string;
  topic: string;
  year: number;
  evidence: AtlasEvidenceProps;
}
const inputStyle =
  "w-full rounded-sm border border-stone-300 bg-white px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-teal-700";

/** Browse supplied links without retrieving, scoring or inferring outcomes in the frontend. */
export function AtlasExplorer({
  links,
  coverageNotes,
}: {
  links: readonly AtlasLinkView[];
  coverageNotes: readonly string[];
}) {
  const [view, setView] = useState<"published" | "audit">("published");
  const [query, setQuery] = useState("");
  const [topic, setTopic] = useState("");
  const [year, setYear] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const topics = [...new Set(links.map((link) => link.topic))].sort();
  const years = [...new Set(links.map((link) => link.year))].sort((a, b) => b - a);
  const viewLinks = links.filter(
    (link) => (link.evidence.assessment.status === "published") === (view === "published"),
  );
  const visible = viewLinks.filter(
    (link) =>
      (!topic || link.topic === topic) &&
      (!year || String(link.year) === year) &&
      `${link.law} ${link.evidence.actor} ${link.evidence.ask}`
        .toLocaleLowerCase("en")
        .includes(query.trim().toLocaleLowerCase("en")),
  );
  const selected = visible.find((link) => link.id === selectedId) ?? visible[0];
  return (
    <section
      aria-label="Influence Atlas explorer"
      className="mx-auto max-w-[1600px] px-5 py-8 sm:px-8"
    >
      <header className="mb-7">
        <p className="text-xs font-medium uppercase tracking-widest text-teal-800">
          Influence Atlas
        </p>
        <h1 className="mt-2 font-serif text-3xl text-stone-900 sm:text-4xl">Follow the evidence</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-stone-600">
          Explore actors' requests, proposed amendments and observed legal outcomes in the loaded
          snapshot.
        </p>
        {coverageNotes.length > 0 && (
          <aside
            aria-label="Source coverage"
            className="mt-5 border-l-2 border-amber-400 pl-4 text-sm leading-6 text-stone-600"
          >
            <h2 className="font-medium text-stone-800">Source coverage</h2>
            <ul className="mt-1 list-disc pl-5">
              {coverageNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </aside>
        )}
      </header>
      <div className="mb-6 grid gap-4 sm:grid-cols-[minmax(0,2fr)_1fr_1fr]">
        <label className="space-y-2 text-xs text-stone-600">
          Search loaded laws and actors
          <input
            type="search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setSelectedId(null);
            }}
            className={inputStyle}
          />
        </label>
        <label className="space-y-2 text-xs text-stone-600">
          Topic
          <select
            value={topic}
            onChange={(event) => {
              setTopic(event.target.value);
              setSelectedId(null);
            }}
            className={inputStyle}
          >
            <option value="">All topics</option>
            {topic && !topics.includes(topic) && (
              <option value={topic}>{topic} (unavailable)</option>
            )}
            {topics.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-2 text-xs text-stone-600">
          Year
          <select
            value={year}
            onChange={(event) => {
              setYear(event.target.value);
              setSelectedId(null);
            }}
            className={inputStyle}
          >
            <option value="">All years</option>
            {year && !years.includes(Number(year)) && (
              <option value={year}>{year} (unavailable)</option>
            )}
            {years.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </div>
      <nav
        aria-label="Evidence views"
        className="mb-5 flex flex-wrap gap-2 border-b border-stone-200 pb-4"
      >
        {(["published", "audit"] as const).map((item) => (
          <button
            key={item}
            type="button"
            aria-pressed={view === item}
            onClick={() => {
              setView(item);
              setSelectedId(null);
            }}
            className={`rounded-sm px-4 py-2 text-sm focus-visible:outline-2 focus-visible:outline-teal-700 ${view === item ? "bg-teal-900 text-white" : "bg-stone-100 text-stone-700"}`}
          >
            {item === "published" ? "Published links" : "Audit candidates"}
          </button>
        ))}
      </nav>
      {view === "audit" && (
        <p className="mb-5 text-sm text-amber-900">
          Unconfirmed and contradicted candidates are excluded from published influence links.
        </p>
      )}
      <p role="status" className="mb-4 text-xs tabular-nums text-stone-500">
        {visible.length} of {viewLinks.length}{" "}
        {view === "published" ? "published links" : "audit candidates"} shown
      </p>
      <div className="grid items-start gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
        <nav
          aria-label="Evidence paths"
          className="max-h-72 space-y-2 overflow-y-auto lg:max-h-[70vh]"
        >
          {visible.map((link) => (
            <button
              key={link.id}
              type="button"
              aria-pressed={selected?.id === link.id}
              onClick={() => setSelectedId(link.id)}
              className={`block w-full rounded-sm border-l-2 p-4 text-left focus-visible:outline-2 focus-visible:outline-teal-700 ${selected?.id === link.id ? "border-teal-800 bg-teal-50" : "border-stone-200 bg-stone-50 hover:bg-stone-100"}`}
            >
              <span className="block text-xs text-stone-500">
                {link.law} · {link.year}
              </span>
              <span className="mt-2 block text-sm font-medium text-stone-900">
                {link.evidence.actor}
              </span>
              <span className="mt-1 block text-xs leading-5 text-stone-600">
                {link.evidence.ask}
              </span>
            </button>
          ))}
        </nav>
        {selected ? (
          <AtlasEvidence key={selected.id} {...selected.evidence} />
        ) : (
          <p className="rounded-sm border border-stone-200 p-8 text-sm leading-6 text-stone-500">
            {view === "published"
              ? viewLinks.length === 0
                ? "No published links available in this snapshot."
                : "No published links match these filters."
              : "No audit candidates match these filters."}
          </p>
        )}
      </div>
    </section>
  );
}
