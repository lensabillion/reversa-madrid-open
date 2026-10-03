"use client";

import { type ReactNode, useState } from "react";
import type {
  AtlasClusterMember,
  AtlasCoordinatedCluster,
  AtlasCoordinatedResult,
  AtlasCoordinatedView,
} from "../lib/atlas-coordinated";

/** The request for the law's clusters, as `useResource` reports it. */
export interface AtlasCoordinatedState {
  data: AtlasCoordinatedResult | null;
  error: string | null;
  retry: () => void;
}

/** Clusters drawn at first and added per click; the AI Act has 269, with every wording quoted. */
const pageSize = 25;
const chipStyle = "rounded-full border px-2.5 py-0.5 text-xs font-medium";
const actionStyle =
  "text-sm text-teal-800 underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-teal-700";

function number(value: number): string {
  return value.toLocaleString("en");
}

function plural(value: number, one: string, many: string): string {
  return `${number(value)} ${value === 1 ? one : many}`;
}

function GroupChips({ groups, label }: { groups: readonly string[]; label: string }) {
  if (groups.length === 0) {
    return (
      <p className="text-xs italic text-stone-500">{label}: unknown (not in the Member data)</p>
    );
  }
  return (
    <ul aria-label={label} className="flex flex-wrap gap-1.5">
      {groups.map((group) => (
        <li key={group} className={`${chipStyle} border-teal-700 bg-white text-teal-900`}>
          {group}
        </li>
      ))}
    </ul>
  );
}

function Member({ member }: { member: AtlasClusterMember }) {
  return (
    <li className="min-w-0 space-y-2 rounded-md border border-stone-200 bg-white p-4 text-sm leading-6">
      <p className="text-xs text-stone-600">
        <span className="font-semibold text-stone-900">
          {member.committee ?? "Committee not recorded"}
        </span>{" "}
        · {member.stage} stage ·{" "}
        {member.tabled_on === null ? "tabling date unknown" : `tabled ${member.tabled_on}`}
      </p>
      <GroupChips groups={member.political_groups} label="Political groups of the authors" />
      <p className="text-stone-700">
        <span className="text-xs uppercase tracking-wide text-stone-500">Tabled by </span>
        {member.author_names.length === 0 ? "authors not recorded" : member.author_names.join(", ")}
      </p>
      <p className="text-xs text-stone-600">
        {member.target_provision ?? "Target provision not recorded"}
      </p>
      <blockquote className="border-l-2 border-teal-700 pl-3 text-stone-900">
        {member.inserted.map((span) => span.text).join(" … ")}
      </blockquote>
      <p className="break-all font-mono text-[11px] text-stone-500">{member.amendment_id}</p>
    </li>
  );
}

function Cluster({ cluster, position }: { cluster: AtlasCoordinatedCluster; position: number }) {
  const [sideBySide, setSideBySide] = useState(false);
  return (
    <li>
      <article
        aria-label={`Cluster ${position}`}
        className="space-y-3 rounded-md border border-stone-300 bg-stone-50 p-4"
      >
        <header className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h3 className="font-serif text-lg text-stone-900">Cluster {position}</h3>
          <span
            className={`${chipStyle} ${cluster.cross_group ? "border-teal-900 bg-teal-900 text-white" : "border-stone-300 bg-white text-stone-600"}`}
          >
            {cluster.cross_group ? "Spans political groups" : "Not marked as spanning groups"}
          </span>
          <GroupChips groups={cluster.political_groups} label="Political groups in this cluster" />
          <p className="text-xs tabular-nums text-stone-600">
            {plural(cluster.members.length, "amendment", "amendments")} · at least{" "}
            {plural(cluster.inserted_words, "inserted word", "inserted words")} each · least similar
            pair {cluster.min_similarity.toFixed(2)}
          </p>
          <button
            type="button"
            aria-expanded={sideBySide}
            onClick={() => setSideBySide((value) => !value)}
            className={actionStyle}
          >
            {sideBySide ? "Stack the amendments" : "Compare side by side"}
          </button>
        </header>
        <ul
          aria-label={`Amendments of cluster ${position}`}
          className={
            sideBySide
              ? "grid auto-cols-[minmax(20rem,1fr)] grid-flow-col gap-3 overflow-x-auto pb-2"
              : "space-y-3"
          }
        >
          {cluster.members.map((member) => (
            <Member key={member.amendment_id} member={member} />
          ))}
        </ul>
      </article>
    </li>
  );
}

function Clusters({ view }: { view: AtlasCoordinatedView }) {
  const [shown, setShown] = useState(pageSize);
  const { counts, clusters } = view;
  const spanning = clusters.filter((cluster) => cluster.cross_group).length;
  return (
    <>
      <div className="rounded-md border border-teal-200 bg-white p-5">
        <p className="font-serif text-2xl text-stone-900">
          {number(spanning)} of {plural(clusters.length, "cluster", "clusters")}{" "}
          {spanning === 1 && clusters.length === 1 ? "spans" : "span"} political groups
        </p>
        <p className="mt-2 text-sm tabular-nums leading-6 text-stone-600">
          {number(counts.compared)} of {plural(counts.amendments, "amendment", "amendments")}{" "}
          compared · {number(counts.too_short)} too short (under {number(view.min_inserted_words)}{" "}
          inserted words) · {number(counts.not_comparable)} not comparable
        </p>
        <p className="mt-1 text-xs leading-5 text-stone-500">
          Method {view.method}: {number(view.shingle_words)}-word runs, similarity threshold{" "}
          {view.similarity_threshold}. Run {view.run_id}, generated {view.generated_at}.
        </p>
      </div>
      {clusters.length === 0 ? (
        <p className="rounded-md border border-stone-200 bg-white p-5 text-sm leading-6 text-stone-600">
          No clusters: among the {plural(counts.compared, "amendment", "amendments")} compared, no
          two insert near-identical wording under this method. This is not a finding that no wording
          was shared: see the limits below.
        </p>
      ) : (
        <>
          <p className="text-sm leading-6 text-stone-600">
            Clusters are listed in the pipeline's order, those spanning political groups first.
            Showing {number(Math.min(shown, clusters.length))} of {number(clusters.length)}.
          </p>
          <ol aria-label="Clusters" className="space-y-4">
            {clusters.slice(0, shown).map((cluster, index) => (
              <Cluster key={cluster.cluster_id} cluster={cluster} position={index + 1} />
            ))}
          </ol>
          {shown < clusters.length && (
            <button
              type="button"
              onClick={() => setShown((value) => value + pageSize)}
              className={actionStyle}
            >
              Show {number(Math.min(pageSize, clusters.length - shown))} more clusters
            </button>
          )}
        </>
      )}
      <section aria-label="Limits of this method" className="text-sm leading-6 text-stone-600">
        <h3 className="font-medium text-stone-900">Limits of this method</h3>
        {view.limitations.length === 0 ? (
          <p>The pipeline supplied no limitations for this cluster file.</p>
        ) : (
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {view.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

/**
 * The law's coordinated amendments: near-identical wording tabled by Members of different
 * groups, exactly as the API lists it. The wording is quoted, never attributed to a drafter.
 */
export function AtlasCoordinated({
  procedureId,
  state,
}: {
  procedureId: string;
  state: AtlasCoordinatedState;
}) {
  let body: ReactNode;
  if (state.error !== null) {
    body = (
      <div role="alert" className="space-y-2 text-sm leading-6 text-stone-600">
        <p className="font-medium text-stone-900">
          The coordinated amendments could not be loaded.
        </p>
        <p className="font-mono text-xs text-red-800">{state.error}</p>
        <p>
          No cluster is shown, because a partial list could mislead. Check that the backend is
          running (make dev-backend), then retry.
        </p>
        <button type="button" onClick={state.retry} className={actionStyle}>
          Retry coordinated amendments
        </button>
      </div>
    );
  } else if (state.data === null) {
    body = (
      <p role="status" className="text-sm text-stone-500">
        Loading coordinated amendments…
      </p>
    );
  } else if (state.data.found) {
    body = <Clusters view={state.data.view} />;
  } else {
    body = (
      <div className="space-y-2 rounded-md border border-stone-200 bg-white p-5 text-sm leading-6 text-stone-600">
        <p className="font-medium text-stone-900">This law has no cluster file yet.</p>
        <p>{state.data.detail}</p>
        <p>
          That is unknown, not zero: the amendments have not been compared. Build the file from the
          repository root with{" "}
          <code className="font-mono text-xs text-stone-800">make atlas LAW='{procedureId}'</code>,
          then reload this page.
        </p>
      </div>
    );
  }
  return (
    <section aria-label="Coordinated amendments" className="min-w-0 space-y-5">
      <header>
        <h2 className="font-serif text-3xl text-stone-900">Coordinated amendments</h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-stone-600">
          Amendments to this law that insert near-identical wording, grouped into clusters.
          Near-identical wording tabled by Members of different groups is listed first. A cluster
          shows that the same wording was tabled more than once; it does not show where the wording
          came from.
        </p>
      </header>
      {body}
    </section>
  );
}
