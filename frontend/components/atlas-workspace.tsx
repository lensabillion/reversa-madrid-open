"use client";

import { type ReactNode, useState } from "react";
import type { AtlasLayerCoverage } from "../lib/atlas-api";
import { AtlasSourceLayers } from "./atlas-coverage";
import { AtlasExplorer, type AtlasLinkView } from "./atlas-explorer";
import { AtlasGraph, type AtlasGraphSnapshot } from "./atlas-graph";

export interface AtlasDataNotice {
  summary: string;
  details: readonly string[];
}

type WorkspaceView = "graph" | "evidence" | "outcomes" | "coordinated";

const disclosureSummary =
  "cursor-pointer font-medium text-teal-800 underline decoration-teal-300 underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-teal-700";

/**
 * Explain the investigation before offering evidence and supplied outcome calculations.
 * `coordinated` adds a fourth view. The workspace always opens on the graph. The explanation and
 * the data notice stay one line until opened, so the graph is in the first screen; source layers
 * follow the graph, or come first when the graph is empty because they say why.
 */
export function AtlasWorkspace({
  snapshot,
  links,
  coverage,
  coverageNotes,
  dataNotice,
  analysis,
  coordinated = null,
}: {
  snapshot: AtlasGraphSnapshot;
  links: readonly AtlasLinkView[];
  coverage: readonly AtlasLayerCoverage[];
  coverageNotes: readonly string[];
  dataNotice: AtlasDataNotice;
  /** A function receives a callback that opens one published link in the Evidence view. */
  analysis: ReactNode | ((openEvidence: (linkId: string) => void) => ReactNode);
  coordinated?: ReactNode;
}) {
  const [view, setView] = useState<WorkspaceView>("graph");
  const views: (readonly [WorkspaceView, string])[] = [
    ["graph", "Explore the graph"],
    ["evidence", "Read the evidence"],
    ["outcomes", "See the outcomes"],
  ];
  if (coordinated !== null) {
    views.push(["coordinated", "Coordinated amendments"]);
  }
  const [selectedLink, setSelectedLink] = useState<string | null>(null);
  const selectedUnavailable =
    selectedLink !== null &&
    !links.some(
      (link) => link.id === selectedLink && link.evidence.assessment.status === "published",
    );
  const sourceLayers = <AtlasSourceLayers coverage={coverage} links={links} />;
  const graphEmpty = snapshot.nodes.length === 0;
  return (
    <main className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-white px-5 py-3 sm:px-8">
        <div className="mx-auto flex max-w-[1536px] flex-wrap items-baseline gap-x-6 gap-y-2 text-sm">
          <h1 className="font-serif text-xl leading-tight">Whose requests appear in EU law?</h1>
          <details className="min-w-0 text-stone-600 open:basis-full">
            <summary className={disclosureSummary}>How does the investigation work?</summary>
            <p className="mt-3 max-w-3xl leading-6">
              Organizations ask lawmakers to change legislation. We connect those requests to
              matching amendments, then check what appears in the final law.
            </p>
            <ol
              aria-label="How to read the investigation"
              className="mt-3 grid gap-4 sm:grid-cols-3"
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
                  <p className="font-semibold text-stone-900">{title}</p>
                  <p className="mt-1 leading-6">{text}</p>
                </li>
              ))}
            </ol>
          </details>
          <section
            aria-label="About these results"
            className="min-w-0 has-[details[open]]:basis-full"
          >
            <details>
              <summary className={disclosureSummary}>
                Coverage, methods and excluded records
              </summary>
              <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 leading-6 text-amber-950">
                <p className="font-medium">{dataNotice.summary}</p>
                <div className="mt-2 max-h-64 overflow-y-auto overscroll-contain border-t border-amber-200 pt-2">
                  <ul className="list-disc space-y-3 pl-5 pr-3 [overflow-wrap:anywhere]">
                    {dataNotice.details.map((detail) => (
                      <li key={detail}>{detail}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </details>
          </section>
        </div>
      </header>
      <div className="mx-auto max-w-[1600px] px-5 py-4 sm:px-8">
        <nav aria-label="Atlas workspace" className="mb-4 flex flex-wrap gap-2">
          {views.map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={view === value}
              onClick={() => setView(value)}
              className={`rounded-full px-4 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 ${view === value ? "bg-teal-900 text-white" : "border border-stone-300 bg-white text-stone-700 hover:bg-stone-100"}`}
            >
              {label}
            </button>
          ))}
        </nav>
        {view === "graph" && (
          <>
            {graphEmpty && sourceLayers}
            <AtlasGraph
              snapshot={snapshot}
              onSelectLink={(linkId) => {
                setSelectedLink(linkId);
                setView("evidence");
              }}
            />
            {!graphEmpty && <div className="mt-6">{sourceLayers}</div>}
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
            {typeof analysis === "function"
              ? analysis((linkId) => {
                  setSelectedLink(linkId);
                  setView("evidence");
                })
              : analysis}
          </section>
        )}
        {view === "coordinated" && coordinated}
      </div>
    </main>
  );
}
