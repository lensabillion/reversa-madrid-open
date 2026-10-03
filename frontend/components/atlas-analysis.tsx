"use client";

import { useSearchParams } from "next/navigation";
import {
  type AtlasFindingsResult,
  atlasFindingsUrl,
  evidenceLine,
  type AtlasFinding as LawFinding,
  plainFinding,
  readAtlasFindings,
} from "../lib/atlas-findings";
import { useResource } from "../lib/use-resource";

/** Presentation citations; a usable URL does not itself validate a pipeline finding. */
export interface AtlasAnalysisSource {
  title: string;
  url: string;
}

/** The pipeline supplies this order and these counts; the view performs no ranking. */
export interface AtlasRankingRow {
  actorId: string;
  actor: string;
  fullWins: number;
  /** All observed asks, including partial, not-observed and unknown final outcomes. */
  observedAsks: number;
  /** Assessed final outcomes: full, partial and not reflected; excludes unknown. */
  assessedAsks: number;
  partial: number;
  notObserved: number;
  unknown: number;
  sources: readonly AtlasAnalysisSource[];
}

/** A supplied finding retains the sources and limitations that support its wording. */
export interface AtlasFinding {
  id: string;
  text: string;
  sources: readonly AtlasAnalysisSource[];
  limitations: readonly string[];
}

const reportSections = ["WHO", "WHAT", "TOWARDS", "HOW", "NEXT"] as const;

/** Local display props, awaiting the shared backend analysis adapter. */
export interface AtlasAnalysisProps {
  sampleLabel: string;
  coverageNotes: readonly string[];
  rankings: readonly AtlasRankingRow[];
  findings: Record<(typeof reportSections)[number], readonly AtlasFinding[]>;
}

function publicSources(sources: readonly AtlasAnalysisSource[]): AtlasAnalysisSource[] {
  return sources.filter((source) => {
    try {
      const url = new URL(source.url);
      return (
        source.title.trim().length > 0 && (url.protocol === "https:" || url.protocol === "http:")
      );
    } catch {
      return false;
    }
  });
}

function Sources({ sources }: { sources: readonly AtlasAnalysisSource[] }) {
  const usable = publicSources(sources);
  return usable.length === 0 ? (
    <p className="text-amber-900">Source evidence unavailable.</p>
  ) : (
    <ul className="space-y-1">
      {usable.map((source) => (
        <li key={`${source.url}:${source.title}`}>
          <a
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="break-words text-teal-800 underline underline-offset-4"
          >
            {source.title}
          </a>
        </li>
      ))}
    </ul>
  );
}

type Section = (typeof reportSections)[number];

/** The findings endpoint's answer for the law named in the URL. */
interface FindingsState {
  data: AtlasFindingsResult | null;
  error: string | null;
}

function ComputedFinding({ finding }: { finding: LawFinding }) {
  return (
    <div className="mt-3 space-y-2 text-sm leading-6">
      {finding.headline !== null && (
        <p className="break-words font-medium">{plainFinding(finding.headline)}</p>
      )}
      {finding.evidence.length > 0 && (
        <p className="break-words text-xs text-stone-600">
          Evidence: {evidenceLine(finding.evidence)}
        </p>
      )}
      {finding.details.length > 0 && (
        <details className="text-xs text-stone-700">
          <summary className="cursor-pointer text-teal-800">
            {finding.details.length} more line{finding.details.length === 1 ? "" : "s"}
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {finding.details.map((line) => (
              <li key={line} className="break-words">
                {plainFinding(line)}
              </li>
            ))}
          </ul>
        </details>
      )}
      {finding.notes.length > 0 && (
        <ul className="space-y-1 text-xs text-amber-900">
          {finding.notes.map((note) => (
            <li key={note}>{plainFinding(note)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** One question's card body from the findings endpoint, or why it has none. */
function EndpointFinding({ section, state }: { section: Section; state: FindingsState | null }) {
  if (state === null) {
    return (
      <p className="mt-3 text-sm leading-6 text-stone-500">
        {section === "NEXT"
          ? "Forecast unavailable: no source-backed forecast supplied."
          : "Evidence gap: no source-backed finding supplied."}
      </p>
    );
  }
  if (state.error !== null) {
    return <p className="mt-3 text-sm leading-6 text-amber-900">Finding could not be loaded.</p>;
  }
  if (state.data === null) {
    return <p className="mt-3 text-sm leading-6 text-stone-500">Loading finding…</p>;
  }
  if (!state.data.found) {
    return (
      <p className="mt-3 text-sm leading-6 text-amber-900">
        Not collected: {plainFinding(state.data.detail)}
      </p>
    );
  }
  const finding = state.data.findings.findings.find((item) => item.question === section);
  if (finding === undefined) {
    return (
      <p className="mt-3 text-sm leading-6 text-amber-900">
        Evidence gap: the backend sent no {section} finding.
      </p>
    );
  }
  return (
    <>
      {finding.status === "computed" ? (
        <ComputedFinding finding={finding} />
      ) : (
        <p className="mt-3 break-words text-sm leading-6 text-amber-900">
          Not run yet:{" "}
          <code className="rounded-sm bg-amber-50 px-1 text-xs">
            {finding.command ?? "no command recorded"}
          </code>
        </p>
      )}
      <p className="mt-2 text-xs leading-5 text-stone-500">
        Limitation: {plainFinding(finding.limitation)}
      </p>
    </>
  );
}

/** Presents observed outcomes and a cited report without estimating influence or forecasts. */
export function AtlasAnalysis({
  sampleLabel,
  coverageNotes,
  rankings,
  findings,
}: AtlasAnalysisProps) {
  // The law browser names the open law in the URL; the findings follow it, as the view does.
  const slug = useSearchParams().get("law") || null;
  const findingsResource = useResource(
    slug === null ? null : atlasFindingsUrl(slug),
    readAtlasFindings,
  );
  const state: FindingsState | null =
    slug === null ? null : { data: findingsResource.data, error: findingsResource.error };
  return (
    <article aria-label="Atlas analysis" className="min-w-0 space-y-8 text-stone-800">
      <header>
        <p className="text-xs font-medium uppercase tracking-wider text-teal-800">
          Observed sample
        </p>
        <h2 className="mt-2 font-serif text-2xl">{sampleLabel}</h2>
        <div className="mt-4 rounded-sm border border-amber-200 bg-amber-50 p-4 text-sm leading-6">
          <h3 className="font-medium">Coverage and limits</h3>
          {coverageNotes.length === 0 ? (
            <p>Coverage information unavailable.</p>
          ) : (
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {coverageNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      </header>
      <section aria-label="Observed outcome rankings" className="min-w-0">
        <h3 className="font-serif text-xl">Observed outcome rankings</h3>
        <p className="mt-2 text-sm leading-6 text-stone-600">
          The denominator includes assessed outcomes, including partial outcomes, and excludes
          unknown outcomes. All observed asks are shown separately for coverage. Counts describe
          this sample; they do not establish causal influence or coverage of all EU law. Row order
          is supplied by the pipeline.
        </p>
        {rankings.length === 0 ? (
          <p className="mt-4 text-sm text-stone-500">
            Rankings unavailable: no observed sample supplied.
          </p>
        ) : (
          <div className="mt-4 overflow-x-auto rounded-sm border border-stone-200">
            <table className="w-full min-w-[42rem] text-left text-sm">
              <caption className="sr-only">
                Outcome counts in the observed sample, in pipeline-supplied order
              </caption>
              <thead className="bg-stone-100 text-xs text-stone-600">
                <tr>
                  {[
                    "Actor",
                    "Fully reflected / assessed asks",
                    "All observed asks",
                    "Partial",
                    "Not reflected",
                    "Unknown",
                    "Evidence",
                  ].map((label) => (
                    <th key={label} scope="col" className="p-3 font-medium">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rankings.map((row) => (
                  <tr key={row.actorId} className="border-t border-stone-200 align-top">
                    <td className="p-3 font-medium">{row.actor}</td>
                    <td className="p-3 tabular-nums">
                      {row.assessedAsks === 0 ? (
                        <>Rate unavailable · {row.fullWins} full wins; 0 assessed asks</>
                      ) : (
                        <>
                          {row.fullWins} / {row.assessedAsks}
                        </>
                      )}
                    </td>
                    <td className="p-3 tabular-nums">{row.observedAsks}</td>
                    <td className="p-3 tabular-nums">{row.partial}</td>
                    <td className="p-3 tabular-nums">{row.notObserved}</td>
                    <td className="p-3 tabular-nums">{row.unknown}</td>
                    <td className="max-w-64 p-3 text-xs leading-6">
                      <Sources sources={row.sources} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {state !== null && state.error !== null && (
        <div role="alert" className="rounded-sm border border-amber-300 bg-amber-50 p-4 text-sm">
          <p>The report's findings could not be loaded: {state.error}</p>
          <button
            type="button"
            onClick={findingsResource.retry}
            className="mt-2 rounded-sm border border-amber-400 px-3 py-1 text-xs"
          >
            Retry findings
          </button>
        </div>
      )}
      {findingsResource.loading && (
        <p role="status" className="text-sm text-stone-500">
          Loading the report's findings…
        </p>
      )}
      <div className="grid gap-5 md:grid-cols-2">
        {reportSections.map((section) => (
          <section
            key={section}
            aria-label={section}
            className="min-w-0 rounded-sm border border-stone-200 bg-white p-5"
          >
            <h3 className="text-xs font-semibold tracking-wider text-teal-800">{section}</h3>
            {findings[section].length === 0 ? (
              <EndpointFinding section={section} state={state} />
            ) : (
              findings[section].map((finding) => (
                <div key={finding.id} className="mt-4 space-y-3 text-sm leading-6">
                  {publicSources(finding.sources).length === 0 ? (
                    <p className="text-amber-900">
                      Evidence gap: supplied finding has no usable public source.
                    </p>
                  ) : (
                    <>
                      <p className="break-words">{finding.text}</p>
                      <Sources sources={finding.sources} />
                      {finding.limitations.length > 0 && (
                        <ul className="list-disc space-y-1 pl-5 text-xs text-stone-500">
                          {finding.limitations.map((limitation) => (
                            <li key={limitation}>{limitation}</li>
                          ))}
                        </ul>
                      )}
                    </>
                  )}
                </div>
              ))
            )}
          </section>
        ))}
      </div>
    </article>
  );
}
