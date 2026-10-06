import type { ReactNode } from "react";
import type { LayerCoverage } from "../lib/coverage";

export function sentence(text: string): string {
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

/** One plain sentence for a layer that is not complete; `null` for a complete layer. */
export function coverageNote(row: LayerCoverage): string | null {
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

/** A full-width message in place of the view; `announce` sets its live-region role. */
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
