import type { LineageMatchKind } from "../lib/lineage-api";

/**
 * One color per method, used everywhere on the lineage page: teal for the lexical analysis
 * (a run of identical words) and violet for the semantic one (reworded wording that Jev
 * judged). Every mark also carries its label, so the method never depends on color alone.
 * The pair passes the dataviz validator on the light surface (normal ΔE 28.5, worst CVD
 * ΔE 20.5); other bars on the page are neutral gray so teal and violet mean only the method.
 */
export const kindStyle: Record<
  LineageMatchKind,
  { label: string; detail: string; mark: string; border: string; badge: string }
> = {
  verbatim: {
    label: "Lexical",
    detail: "the same words, found word for word",
    mark: "bg-teal-600",
    border: "border-teal-600",
    badge: "bg-teal-50 text-teal-900 ring-1 ring-teal-600/40",
  },
  semantic: {
    label: "Semantic",
    detail: "other words, judged by Jev; unconfirmed",
    mark: "bg-violet-600",
    border: "border-violet-600",
    badge: "bg-violet-50 text-violet-900 ring-1 ring-violet-600/40",
  },
};

export function KindBadge({ kind, note }: { kind: LineageMatchKind; note?: string | null }) {
  const style = kindStyle[kind];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs ${style.badge}`}
    >
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${style.mark}`} />
      {style.label}
      {note === undefined || note === null ? "" : ` · ${note}`}
    </span>
  );
}

/** The key to both colors, shown wherever the two methods appear together. */
export function KindLegend() {
  return (
    <ul aria-label="Analysis methods" className="flex flex-wrap gap-x-5 gap-y-2 text-xs">
      {(["verbatim", "semantic"] as const).map((kind) => (
        <li key={kind} className="flex items-center gap-2 text-stone-700">
          <KindBadge kind={kind} />
          <span>{kindStyle[kind].detail}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * A two-segment bar, lexical then semantic, anchored at zero with a 2px gap between fills,
 * and both numbers as text beside it.
 */
export function KindSplitBar({
  lexical,
  semantic,
  max,
}: {
  lexical: number;
  semantic: number;
  max: number;
}) {
  const width = (value: number) => (max === 0 || value === 0 ? 0 : (value / max) * 100);
  return (
    <span className="flex items-center gap-2" title={`Lexical ${lexical}, semantic ${semantic}`}>
      <span aria-hidden="true" className="flex h-2 w-24 shrink-0 gap-[2px] rounded-sm bg-stone-100">
        {lexical > 0 && (
          <span
            className={`block h-2 rounded-l-sm ${kindStyle.verbatim.mark}`}
            style={{ width: `${width(lexical)}%` }}
          />
        )}
        {semantic > 0 && (
          <span
            className={`block h-2 rounded-r-[4px] ${kindStyle.semantic.mark}`}
            style={{ width: `${width(semantic)}%` }}
          />
        )}
      </span>
      <span className="tabular-nums">
        {lexical + semantic}
        {semantic > 0 && (
          <span className="text-xs text-stone-500">
            {" "}
            ({lexical} lex · {semantic} sem)
          </span>
        )}
      </span>
    </span>
  );
}
