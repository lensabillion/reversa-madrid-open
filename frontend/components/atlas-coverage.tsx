import type { AtlasLayer, AtlasLayerCoverage, AtlasLayerStatus } from "../lib/atlas-api";
import type { AtlasLinkView } from "./atlas-explorer";

const layerLabels = {
  metadata: "Procedure metadata",
  proposal: "Commission proposal",
  parliament_position: "Parliament position",
  final_act: "Final act",
  committee_amendments: "Committee amendments",
  plenary_amendments: "Plenary amendments",
  asks: "Consultation feedback",
  actors: "Actors",
  meetings: "Meetings",
  votes: "Votes",
} satisfies Record<AtlasLayer, string>;

interface StatusDisplay {
  label: string;
  /** Read after the layer name when the layer blocks links, e.g. "is missing". */
  verb: string;
  /** Whether the layer supplied any records the pipeline could link. */
  supplied: boolean;
  tone: string;
  dot: string;
}

function statusDisplay(status: AtlasLayerStatus): StatusDisplay {
  switch (status) {
    case "complete":
      return {
        label: "complete",
        verb: "is complete",
        supplied: true,
        tone: "border-teal-300 bg-teal-50 text-teal-950",
        dot: "bg-teal-600",
      };
    case "partial":
      return {
        label: "partial",
        verb: "is partial",
        supplied: true,
        tone: "border-amber-300 bg-amber-50 text-amber-950",
        dot: "bg-amber-500",
      };
    case "stale":
      return {
        label: "stale",
        verb: "is stale",
        supplied: true,
        tone: "border-amber-300 bg-amber-50 text-amber-950",
        dot: "bg-amber-500",
      };
    case "missing":
      return {
        label: "missing",
        verb: "is missing",
        supplied: false,
        tone: "border-red-300 bg-red-50 text-red-950",
        dot: "bg-red-600",
      };
    case "not_collected":
      return {
        label: "not collected",
        verb: "was not collected",
        supplied: false,
        // The run did not try (e.g. no connector yet): a known gap, not a failed download.
        tone: "border-stone-300 bg-stone-100 text-stone-800",
        dot: "bg-stone-500",
      };
    case "not_applicable":
      return {
        label: "not applicable",
        verb: "does not apply to this law",
        supplied: false,
        tone: "border-stone-300 bg-white text-stone-700",
        dot: "bg-stone-400",
      };
    default: {
      const unhandled: never = status;
      throw new Error(`Unknown coverage status: ${String(unhandled)}`);
    }
  }
}

function reasonText(row: AtlasLayerCoverage): string {
  return (row.reason ?? "no reason was recorded").replace(/[.!?]$/, "");
}

/** One clause per link input that supplied nothing, e.g. "consultation feedback is missing: …". */
function blockers(coverage: readonly AtlasLayerCoverage[]): string[] {
  const rows = new Map(coverage.map((row) => [row.layer, row]));
  const blocked = (layer: AtlasLayer): string | null => {
    const row = rows.get(layer);
    const name = layerLabels[layer].toLocaleLowerCase("en");
    if (row === undefined) {
      return `${name} has no coverage record`;
    }
    const status = statusDisplay(row.status);
    return status.supplied ? null : `${name} ${status.verb}: ${reasonText(row)}`;
  };
  // Links join requests to amendments: one amendment layer is enough, requests are not optional.
  const asks = blocked("asks");
  const committee = blocked("committee_amendments");
  const plenary = blocked("plenary_amendments");
  return [
    ...(asks === null ? [] : [asks]),
    ...(committee !== null && plenary !== null ? [committee, plenary] : []),
  ];
}

function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString("en")} ${count === 1 ? one : many}`;
}

/** Why the graph has no published link: data the links need is absent, or nothing passed. */
export function emptyGraphReason(
  coverage: readonly AtlasLayerCoverage[],
  links: readonly AtlasLinkView[],
): string {
  const missing = blockers(coverage);
  if (missing.length > 0) {
    return `No links can be shown because ${missing.join("; and ")}.`;
  }
  const degraded = coverage.some(
    (row) =>
      (row.layer === "asks" ||
        row.layer === "committee_amendments" ||
        row.layer === "plenary_amendments") &&
      row.status !== "complete",
  );
  const checked =
    links.length === 0
      ? "No candidate link reached the audit view, so none met the publication bar."
      : `${plural(links.length, "candidate link was", "candidate links were")} checked and kept for audit as unconfirmed or contradicted; none met the publication bar.`;
  return [
    "Consultation feedback and amendments were collected, but no link was published.",
    checked,
    "Candidates with insufficient evidence are not counted.",
    ...(degraded ? ["Some of those layers are incomplete; see their badges."] : []),
  ].join(" ");
}

/**
 * One badge per source layer on the opening graph view, so missing data is told apart from no
 * discovered influence without switching tabs. Status is spelled out, never shown by colour alone.
 */
export function AtlasSourceLayers({
  coverage,
  links,
}: {
  coverage: readonly AtlasLayerCoverage[];
  links: readonly AtlasLinkView[];
}) {
  const published = links.filter((link) => link.evidence.assessment.status === "published");
  return (
    <section aria-label="Source layers" className="mb-6 min-w-0 space-y-3">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.13em] text-stone-600">
        Source layers
      </h2>
      {coverage.length === 0 ? (
        <p className="text-sm text-stone-600">This run recorded no source coverage.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {coverage.map((row) => {
            const status = statusDisplay(row.status);
            return (
              <li
                key={row.layer}
                className={`min-w-0 max-w-full rounded-md border px-3 py-2 text-xs leading-5 sm:max-w-sm ${status.tone}`}
              >
                <span className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className={`size-2 shrink-0 rounded-full ${status.dot}`}
                  />
                  <span>
                    <span className="font-medium">{layerLabels[row.layer]}</span>
                    {` · ${status.label}`}
                    {row.count === null ? "" : ` · ${row.count.toLocaleString("en")}`}
                  </span>
                </span>
                {row.reason !== null && (
                  <span className="mt-1 block [overflow-wrap:anywhere]">
                    <span className="sr-only">Reason: </span>
                    {row.reason}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {published.length === 0 && (
        <p className="max-w-3xl rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950">
          {emptyGraphReason(coverage, links)}
        </p>
      )}
    </section>
  );
}

/** The run's mode labels (plan §6): what this law's Atlas cannot show, said before the data. */
export function AtlasModes({ modes }: { modes: readonly string[] }) {
  if (modes.length === 0) {
    return null;
  }
  return (
    <ul aria-label="Result modes" className="flex flex-wrap gap-2">
      {modes.map((mode) => (
        <li
          key={mode}
          className="rounded-full border border-amber-400 bg-amber-100 px-4 py-1.5 text-sm font-semibold text-amber-950"
        >
          {mode}
        </li>
      ))}
    </ul>
  );
}
