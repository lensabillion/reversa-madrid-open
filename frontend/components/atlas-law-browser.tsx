"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type ReactNode, useMemo } from "react";
import { atlasLinkViews } from "../lib/atlas";
import {
  AtlasApiError,
  type AtlasLawSummary,
  type AtlasLayerCoverage,
  type AtlasView,
  atlasLawsUrl,
  atlasViewUrl,
  readAtlasLaws,
  readAtlasView,
} from "../lib/atlas-api";
import { useResource } from "../lib/use-resource";
import { AtlasAnalysis, type AtlasAnalysisProps, type AtlasRankingRow } from "./atlas-analysis";
import type { AtlasLinkView } from "./atlas-explorer";
import { type AtlasDataNotice, AtlasWorkspace } from "./atlas-workspace";

const buildCommand = "make atlas LAW='2021/0106(COD)'";
const noFindings: AtlasAnalysisProps["findings"] = {
  WHO: [],
  WHAT: [],
  TOWARDS: [],
  HOW: [],
  NEXT: [],
};

/** A law without an Atlas run is an expected answer here, not a failure to load. */
type LawViewResult = { found: true; view: AtlasView } | { found: false; detail: string };

async function readLawView(url: string, signal: AbortSignal): Promise<LawViewResult> {
  try {
    return { found: true, view: await readAtlasView(url, signal) };
  } catch (error: unknown) {
    if (error instanceof AtlasApiError && error.status === 404) {
      return { found: false, detail: error.detail };
    }
    throw error;
  }
}

export function sentence(text: string): string {
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

/** One plain sentence for a layer that is not complete; `null` for a complete layer. */
export function coverageNote(row: AtlasLayerCoverage): string | null {
  let state: string;
  switch (row.status) {
    case "complete":
      return null;
    case "partial":
      state = "partly collected";
      break;
    case "missing":
      state = "missing from the source";
      break;
    case "stale":
      state = "stale, because the source stopped updating";
      break;
    case "not_applicable":
      state = "not applicable to this law";
      break;
    case "not_collected":
      state = "not collected in this run";
      break;
    default: {
      const unhandled: never = row.status;
      throw new Error(`Unknown coverage status: ${String(unhandled)}`);
    }
  }
  const layer = row.layer.replaceAll("_", " ");
  const reason = row.reason === null ? "No reason was recorded." : sentence(row.reason);
  return `${layer.charAt(0).toUpperCase()}${layer.slice(1)}: ${state}. ${reason}`;
}

/** Display props for one law, or an error: never a partial or repaired view. */
interface LawAtlas {
  links: AtlasLinkView[];
  coverageNotes: string[];
  dataNotice: AtlasDataNotice;
  rankings: AtlasRankingRow[];
}

/** Throws when the view breaks the contract; `atlasLinkViews` checks every join and quote. */
function prepareLawAtlas(view: AtlasView): LawAtlas {
  if (view.schema_version !== "atlas-view-1") {
    throw new Error(`Unsupported Atlas view schema: ${String(view.schema_version)}`);
  }
  if (view.snapshot.schema_version !== "atlas-1") {
    throw new Error(`Unsupported Atlas graph schema: ${String(view.snapshot.schema_version)}`);
  }
  const links = atlasLinkViews(view.bundle);
  const gaps = view.coverage.flatMap((row) => {
    const note = coverageNote(row);
    return note === null ? [] : [note];
  });
  const complete = view.coverage.length > 0 && gaps.length === 0;
  return {
    links,
    coverageNotes: complete ? ["Every source layer recorded for this law is complete."] : gaps,
    dataNotice: {
      summary:
        view.ask_method === "passage-v0"
          ? "Counts represent submission passages, not distinct requests."
          : "Results reflect the recorded method and available source material.",
      details: [
        `Ask extraction method: ${view.ask_method}.`,
        ...(view.limitations.length > 0
          ? view.limitations.map(sentence)
          : ["The pipeline supplied no limitations for this run."]),
      ],
    },
    // The backend orders rankings; this view must not re-rank them.
    rankings: view.rankings.map((row) => ({
      actorId: row.actor_id,
      actor: row.actor_name,
      fullWins: row.full,
      observedAsks: row.observed_asks,
      assessedAsks: row.assessed_asks,
      partial: row.partial,
      notObserved: row.not_observed,
      unknown: row.unknown,
      sources: [],
    })),
  };
}

type Prepared = { ok: true; atlas: LawAtlas } | { ok: false; error: string };

/** A full-width message in place of the workspace; `announce` sets its live-region role. */
export function StateMessage({
  announce,
  title,
  children,
}: {
  announce: "status" | "alert" | null;
  title: string;
  children: ReactNode;
}) {
  return (
    <main className="mx-auto max-w-[1536px] px-5 py-10 sm:px-8">
      <section
        role={announce ?? undefined}
        className="max-w-3xl space-y-3 text-sm leading-6 text-stone-600"
      >
        <h2 className="font-serif text-2xl text-stone-900">{title}</h2>
        {children}
      </section>
    </main>
  );
}

export const retryStyle =
  "text-teal-800 underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-teal-700";

function LawAtlasView({ view, onRetry }: { view: AtlasView; onRetry: () => void }) {
  const prepared = useMemo<Prepared>(() => {
    try {
      return { ok: true, atlas: prepareLawAtlas(view) };
    } catch (error: unknown) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  }, [view]);
  if (!prepared.ok) {
    return (
      <StateMessage announce="alert" title={`The Atlas data for ${view.title} is invalid`}>
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
  const { atlas } = prepared;
  return (
    <>
      <p className="mx-auto max-w-[1536px] px-5 py-3 text-xs text-stone-500 sm:px-8">
        <span className="font-medium text-stone-800">{view.title}</span> · {view.procedure_id} ·
        Atlas run {view.run_id}, generated {view.generated_at}
      </p>
      <AtlasWorkspace
        snapshot={view.snapshot}
        links={atlas.links}
        coverage={view.coverage}
        coverageNotes={atlas.coverageNotes}
        dataNotice={atlas.dataNotice}
        analysis={
          <AtlasAnalysis
            sampleLabel={`${view.title}, ${view.procedure_id}: final-act outcomes of Atlas run ${view.run_id}`}
            coverageNotes={atlas.coverageNotes}
            rankings={atlas.rankings}
            findings={noFindings}
          />
        }
      />
    </>
  );
}

function LawContent({ slug, law }: { slug: string; law: AtlasLawSummary | null }) {
  const result = useResource(atlasViewUrl(slug), readLawView);
  const name = law === null ? slug : law.title;
  if (result.error !== null) {
    return (
      <StateMessage announce="alert" title={`The Atlas for ${name} could not be loaded`}>
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
      <StateMessage announce="status" title={`Loading the Atlas for ${name}…`}>
        <p>Reading the law's graph, evidence and outcome counts from the backend.</p>
      </StateMessage>
    );
  }
  if (!result.data.found) {
    return (
      <StateMessage announce="alert" title={`No Atlas run for ${name}`}>
        <p>{result.data.detail}</p>
        <p>
          Build it from the repository root with its procedure reference, for example{" "}
          <code className="font-mono text-xs text-stone-800">{buildCommand}</code>, then reload this
          page.
        </p>
      </StateMessage>
    );
  }
  return <LawAtlasView view={result.data.view} onRetry={result.retry} />;
}

function linkCount(count: number): string {
  return `${count.toLocaleString("en")} published ${count === 1 ? "link" : "links"}`;
}

/**
 * Lists the laws with a built Atlas run and opens the one named by `?law=`, so a reload or a
 * shared link reopens it. Selection uses the history API, which Next.js syncs with
 * `useSearchParams`, so back and forward move between laws without a page load.
 */
export function AtlasLawBrowser() {
  const searchParams = useSearchParams();
  const selected = searchParams.get("law") || null;
  const laws = useResource(atlasLawsUrl, readAtlasLaws);
  const collected = laws.data?.laws ?? null;
  function select(slug: string) {
    if (slug === selected) {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    params.set("law", slug);
    window.history.pushState(null, "", `?${params.toString()}`);
  }
  return (
    <div className="min-h-dvh bg-stone-50 text-stone-900">
      <header className="flex h-[76px] items-center justify-between gap-4 border-b border-stone-200 bg-white px-5 sm:px-8">
        <div className="flex items-center gap-4">
          <span className="text-xl font-semibold tracking-tight text-stone-900">Influence</span>
          <span className="hidden h-5 w-px bg-stone-300 sm:block" />
          <span className="hidden text-sm text-stone-500 sm:block">Atlas explorer</span>
        </div>
        <Link
          href="/"
          className="rounded-sm px-3 py-2 text-xs font-medium text-stone-500 hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
        >
          Evidence workspace
        </Link>
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
              No law has an Atlas run yet. Build one from the repository root, for example{" "}
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
                      {law.procedure_id} · {linkCount(law.published_links)}
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
            <p>Open a collected law to see whose requests reached its amendments and final text.</p>
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
