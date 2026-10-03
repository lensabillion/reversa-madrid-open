"use client";

import { type ReactNode, useState } from "react";
import type { AtlasLayerCoverage } from "../lib/atlas-api";
import { AtlasSourceLayers } from "./atlas-coverage";
import { AtlasExplorer, type AtlasLinkView } from "./atlas-explorer";
import { AtlasGraph, type AtlasGraphSnapshot } from "./atlas-graph";

/** Explain the investigation before offering evidence and supplied outcome calculations. */
export function AtlasWorkspace({
  snapshot,
  links,
  coverage,
  coverageNotes,
  dataNotice,
  analysis,
}: {
  snapshot: AtlasGraphSnapshot;
  links: readonly AtlasLinkView[];
  coverage: readonly AtlasLayerCoverage[];
  coverageNotes: readonly string[];
  dataNotice: string;
  analysis: ReactNode;
}) {
  const [view, setView] = useState<"graph" | "evidence" | "outcomes">("graph");
  const [selectedLink, setSelectedLink] = useState<string | null>(null);
  const selectedUnavailable =
    selectedLink !== null &&
    !links.some(
      (link) => link.id === selectedLink && link.evidence.assessment.status === "published",
    );
  return (
    <main className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-white px-5 py-6 sm:px-8">
        <div className="mx-auto max-w-[1536px]">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-800">
            Influence Atlas
          </p>
          <h1 className="mt-3 max-w-3xl font-serif text-3xl leading-tight sm:text-4xl">
            Whose requests appear in EU law?
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-stone-600">
            Organizations ask lawmakers to change legislation. We connect those requests to matching
            amendments, then check what appears in the final law.
          </p>
          <details className="mt-4 text-sm text-stone-600">
            <summary className="cursor-pointer font-medium text-teal-800">
              How does the investigation work?
            </summary>
            <ol
              aria-label="How to read the investigation"
              className="mt-6 grid gap-4 text-sm sm:grid-cols-3"
            >
              {[
                ["1. Who asked?", "Read the organization's request in its public submission."],
                ["2. What matched?", "Compare the request with a proposed change to the law."],
                [
                  "3. What survived?",
                  "Check whether the requested change appears in the final text.",
                ],
              ].map(([title, text]) => (
                <li key={title} className="border-l-2 border-teal-700 pl-4">
                  <p className="font-semibold">{title}</p>
                  <p className="mt-1 leading-6 text-stone-600">{text}</p>
                </li>
              ))}
            </ol>
          </details>
          <p className="mt-6 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950">
            {dataNotice}
          </p>
        </div>
      </header>
      <div className="mx-auto max-w-[1600px] px-5 py-6 sm:px-8">
        <nav aria-label="Atlas workspace" className="mb-6 flex flex-wrap gap-2">
          {(
            [
              ["graph", "Explore the graph"],
              ["evidence", "Read the evidence"],
              ["outcomes", "See the outcomes"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={view === value}
              onClick={() => setView(value)}
              className={`rounded-full px-5 py-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 ${view === value ? "bg-teal-900 text-white" : "border border-stone-300 bg-white text-stone-700 hover:bg-stone-100"}`}
            >
              {label}
            </button>
          ))}
        </nav>
        {view === "graph" && (
          <>
            <AtlasSourceLayers coverage={coverage} links={links} />
            <AtlasGraph
              snapshot={snapshot}
              onSelectLink={(linkId) => {
                setSelectedLink(linkId);
                setView("evidence");
              }}
            />
          </>
        )}
        {view === "evidence" && selectedUnavailable && (
          <p role="alert" className="rounded-md border border-amber-300 bg-amber-50 p-5 text-sm">
            Evidence for this graph connection is unavailable in the loaded records. Choose another
            connection or reload a complete snapshot.
          </p>
        )}
        {view === "evidence" && !selectedUnavailable && (
          <AtlasExplorer
            key={selectedLink ?? "all"}
            links={links}
            coverageNotes={coverageNotes}
            initialSelectedId={selectedLink}
          />
        )}
        {view === "outcomes" && (
          <section aria-label="What reached the final law">
            <h2 className="font-serif text-3xl">What reached the final law?</h2>
            <p className="mb-6 mt-3 max-w-3xl text-sm leading-6 text-stone-600">
              These counts show how many requests were fully reflected, partly reflected, or absent
              from the final text. Requests with unknown outcomes stay separate. Getting the
              requested result does not prove that an organization caused it.
            </p>
            {analysis}
          </section>
        )}
      </div>
    </main>
  );
}
