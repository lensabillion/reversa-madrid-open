import type { AtlasLayerCoverage, AtlasLayerStatus } from "../lib/atlas-api";

/** The status in plain words, and the badge colours that set it apart from the others. */
function statusDisplay(status: AtlasLayerStatus): { label: string; style: string } {
  switch (status) {
    case "complete":
      return { label: "Complete", style: "border-emerald-300 bg-emerald-50 text-emerald-950" };
    case "partial":
      return { label: "Partial", style: "border-amber-300 bg-amber-50 text-amber-950" };
    case "missing":
      return { label: "Missing from the source", style: "border-red-300 bg-red-50 text-red-950" };
    case "stale":
      return { label: "Stale", style: "border-orange-300 bg-orange-50 text-orange-950" };
    case "not_applicable":
      return { label: "Not applicable", style: "border-stone-300 bg-stone-100 text-stone-700" };
    case "not_collected":
      return {
        label: "Not collected in this run",
        style: "border-dashed border-stone-400 bg-white text-stone-700",
      };
    default: {
      const unhandled: never = status;
      throw new Error(`Unknown coverage status: ${String(unhandled)}`);
    }
  }
}

function layerName(layer: string): string {
  const words = layer.replaceAll("_", " ");
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}`;
}

/**
 * One badge per source layer of the law: its status, its count and, unless the layer is
 * complete, the pipeline's reason. A count the run did not make reads "not counted", never 0.
 */
export function AtlasCoverageBadges({ coverage }: { coverage: readonly AtlasLayerCoverage[] }) {
  if (coverage.length === 0) {
    return (
      <p className="text-sm text-stone-600">
        Coverage unknown: this run recorded no source layers.
      </p>
    );
  }
  return (
    <ul aria-label="Source layers" className="flex flex-wrap gap-2">
      {coverage.map((row) => {
        const { label, style } = statusDisplay(row.status);
        return (
          <li
            key={row.layer}
            className={`max-w-xs rounded-md border px-3 py-2 text-xs leading-5 ${style}`}
          >
            <p className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-semibold">{layerName(row.layer)}</span>
              <span className="tabular-nums">
                {row.count === null ? "not counted" : row.count.toLocaleString("en")}
              </span>
            </p>
            <p className="font-medium uppercase tracking-wide">{label}</p>
            {row.status !== "complete" && (
              <p className="mt-1">{row.reason ?? "No reason was recorded."}</p>
            )}
          </li>
        );
      })}
    </ul>
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
