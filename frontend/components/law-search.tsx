"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import {
  type BuildState,
  type BuildStep,
  type LawHit,
  type LawSearch as LawSearchAnswer,
  readBuild,
  searchLaws,
  startBuild,
} from "../lib/law-search";

/** How often a running build is polled, in milliseconds. */
export const BUILD_POLL_MS = 2000;
const LOG_LINES = 5;

const buttonStyle =
  "rounded-sm border border-stone-300 bg-white px-3 py-1.5 text-sm font-medium text-stone-800 hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:opacity-60";

interface LawSearchProps {
  /** The page's view: it decides which build counts as built and which step to run. */
  view: BuildStep;
  /** Opens a law that is already built, through the page's `?law=` handling. */
  onOpen: (slug: string) => void;
  /** Called once a build finishes, so the page reloads its law list and opens the law. */
  onBuilt: (slug: string) => void;
}

type Search =
  | { phase: "idle" }
  | { phase: "searching" }
  | { phase: "answer"; answer: LawSearchAnswer }
  | { phase: "error"; detail: string };

export function LawSearch({ view, onOpen, onBuilt }: LawSearchProps) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<Search>({ phase: "idle" });
  const [picked, setPicked] = useState<LawHit | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = query.trim();
    if (text === "") {
      setSearch({ phase: "error", detail: "Type a law to search for." });
      return;
    }
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    setPicked(null);
    setSearch({ phase: "searching" });
    try {
      const result = await searchLaws(text, current.signal);
      if (!current.signal.aborted) {
        setSearch(
          result.ok
            ? { phase: "answer", answer: result.value }
            : { phase: "error", detail: result.detail },
        );
      }
    } catch (error: unknown) {
      if (!current.signal.aborted) {
        setSearch({
          phase: "error",
          detail: error instanceof Error ? error.message : "The search failed.",
        });
      }
    }
  }

  const answer = search.phase === "answer" ? search.answer : null;
  const hit = picked ?? (answer?.status === "found" ? answer.law : null);
  return (
    <section aria-label="Law search" className="min-w-0 max-w-3xl">
      <form onSubmit={(event) => void submit(event)} className="flex min-w-0 flex-wrap gap-2">
        <label htmlFor={`law-search-${view}`} className="basis-full text-sm text-stone-700">
          Search any EU law
        </label>
        <input
          id={`law-search-${view}`}
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="AI Act, 2021/0106(COD), 32024R1689, COM(2021)206…"
          className="min-w-0 flex-1 rounded-sm border border-stone-300 bg-white px-3 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
        />
        <button type="submit" className={buttonStyle} disabled={search.phase === "searching"}>
          Search
        </button>
      </form>
      <div className="mt-2 text-sm leading-6 text-stone-700">
        {search.phase === "searching" && <p role="status">Searching…</p>}
        {search.phase === "error" && <p role="alert">{search.detail}</p>}
        {answer?.status === "not_found" && (
          <p role="status">{answer.message ?? "No EU law matches this search."}</p>
        )}
        {answer?.status === "ambiguous" && hit === null && (
          <div>
            <p>{answer.message ?? "Several laws match. Choose one:"}</p>
            <ul className="mt-1 flex flex-wrap gap-2">
              {answer.choices.map((choice) => (
                <li key={choice.slug} className="min-w-0">
                  <button
                    type="button"
                    onClick={() => setPicked(choice)}
                    className={`${buttonStyle} text-left`}
                  >
                    {choice.title} ({choice.procedure_id})
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {hit !== null && (
          <LawResult key={hit.slug} hit={hit} view={view} onOpen={onOpen} onBuilt={onBuilt} />
        )}
      </div>
    </section>
  );
}

type Build =
  | { phase: "idle" }
  | { phase: "starting" }
  | { phase: "tracking"; build: BuildState }
  | { phase: "error"; detail: string };

function initialBuild(hit: LawHit): Build {
  const running =
    hit.build !== null && (hit.build.state === "queued" || hit.build.state === "running");
  return running && hit.build !== null
    ? { phase: "tracking", build: hit.build }
    : { phase: "idle" };
}

function LawResult({
  hit,
  view,
  onOpen,
  onBuilt,
}: {
  hit: LawHit;
  view: BuildStep;
  onOpen: (slug: string) => void;
  onBuilt: (slug: string) => void;
}) {
  const built = view === "lineage" ? hit.has_lineage : hit.has_atlas;
  const [build, setBuild] = useState<Build>(() => initialBuild(hit));
  const notified = useRef(false);
  const tracked = build.phase === "tracking" ? build.build : null;

  // Chains one timeout per answer, so a slow answer never overlaps the next poll.
  useEffect(() => {
    if (tracked === null || (tracked.state !== "queued" && tracked.state !== "running")) {
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const result = await readBuild(tracked.slug, controller.signal);
          if (!controller.signal.aborted) {
            setBuild(
              result.ok
                ? { phase: "tracking", build: result.value }
                : { phase: "error", detail: result.detail },
            );
          }
        } catch (error: unknown) {
          if (!controller.signal.aborted) {
            setBuild({
              phase: "error",
              detail: error instanceof Error ? error.message : "The build could not be read.",
            });
          }
        }
      })();
    }, BUILD_POLL_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [tracked]);

  useEffect(() => {
    if (tracked?.state === "done" && !notified.current) {
      notified.current = true;
      onBuilt(tracked.slug);
    }
  }, [tracked, onBuilt]);

  async function start() {
    notified.current = false;
    setBuild({ phase: "starting" });
    const result = await startBuild(hit.slug, [view]);
    setBuild(
      result.ok
        ? { phase: "tracking", build: result.value }
        : { phase: "error", detail: result.detail },
    );
  }

  return (
    <div className="mt-1 min-w-0 rounded-sm border border-stone-200 bg-stone-50 p-3">
      <p className="break-words font-medium text-stone-900">{hit.title}</p>
      <p className="text-xs tabular-nums text-stone-500">{hit.procedure_id}</p>
      {built ? (
        <a
          href={`?law=${encodeURIComponent(hit.slug)}`}
          onClick={(event) => {
            event.preventDefault();
            onOpen(hit.slug);
          }}
          className="mt-2 inline-block font-medium text-teal-800 underline"
        >
          Open
        </a>
      ) : (
        <div className="mt-2">
          {build.phase === "idle" && (
            <button type="button" onClick={() => void start()} className={buttonStyle}>
              Build it now
            </button>
          )}
          <div aria-live="polite" className="min-w-0">
            {build.phase === "starting" && <p>Starting the build…</p>}
            {tracked !== null && <BuildProgress build={tracked} />}
            {build.phase === "error" && <p>{build.detail}</p>}
          </div>
          {(build.phase === "error" || tracked?.state === "failed") && (
            <button type="button" onClick={() => void start()} className={`${buttonStyle} mt-2`}>
              Try again
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function BuildProgress({ build }: { build: BuildState }) {
  const log = build.log.slice(-LOG_LINES);
  return (
    <div>
      <p>
        Build {build.state}
        {build.step === null ? "" : `: ${build.step}`}
      </p>
      {build.state === "failed" && <p>{build.error ?? "The build failed without a reason."}</p>}
      {log.length > 0 && (
        <pre className="mt-1 max-w-full overflow-x-auto whitespace-pre-wrap break-words font-mono text-xs text-stone-600">
          {log.join("\n")}
        </pre>
      )}
    </div>
  );
}
