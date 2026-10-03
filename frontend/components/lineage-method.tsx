import type { AtlasLayer, AtlasLayerCoverage, AtlasLayerStatus } from "../lib/atlas-api";
import type { LineageCounts, LineageView } from "../lib/lineage-api";
import { KindBadge } from "./lineage-kind";

const count = new Intl.NumberFormat("en-US");

function known(value: number | null): string {
  return value === null ? "unknown" : count.format(value);
}

interface MethodStep {
  id: string;
  title: string;
  question: string;
  rules: readonly string[];
  result: string;
}

function stepsFor(view: LineageView): readonly MethodStep[] {
  const { counts } = view;
  return [
    {
      id: "compare",
      title: "Compare the two texts",
      question: "What did the final law add to the Commission's proposal?",
      rules: [
        "Any 8 words in a row in the final law that the proposal does not have are new.",
        "Capitals and punctuation are ignored.",
      ],
      result: `${known(counts.changed_units)} of ${known(counts.final_units)} words are new`,
    },
    {
      id: "amendment",
      title: "Find the amendment",
      question: "Which Parliament amendment wrote that new wording?",
      rules: [
        "An amendment wrote the same 8 or more words, and inserted at least one of them.",
        "The stretch holds 3 or more words specific to this law, so boilerplate does not count.",
      ],
      result: `${known(counts.adopted_phrases)} phrases from ${known(counts.amendments_adopting)} amendments`,
    },
    {
      id: "origin",
      title: "Find who said it first",
      question: "Which consultation document asked for it before Parliament did?",
      rules: [
        "The document has the same 8 or more words, or Jev judges it asks for the same legal change (all four of its answers at 0.67 or more).",
        "It was published before every amendment carrying the wording.",
        "Quotes of legal titles and Official Journal references are not counted: same words, but not a request.",
      ],
      result: `${known(counts.documents_with_origin)} of ${known(counts.documents_read)} documents`,
    },
    {
      id: "rank",
      title: "Rank and check",
      question: "Who got their wording in, and can a reader verify it?",
      rules: [
        "Everyone who carried a phrase gets whole credit; shared phrases are marked joint.",
        "Members and groups are ranked by the share of their amendments that made it in.",
        "Three links drawn at random, side by side, with a seed to repeat the draw.",
      ],
      result: "Who, How and Check 3 links tabs",
    },
  ];
}

interface DataSource {
  id: string;
  name: string;
  publisher: string;
  url: string;
  gives: string;
  /**
   * The coverage rows this source fills, each with the unit its count is in. A row with
   * `words` shows that word total from `counts` instead of the row's provision count, since
   * provisions are split differently in the proposal and the final act.
   */
  layers: readonly {
    layer: AtlasLayer;
    unit: string;
    words?: "proposal_units" | "final_units";
  }[];
}

const SOURCES: readonly DataSource[] = [
  {
    id: "texts",
    name: "Commission proposal and final law",
    publisher: "EU Publications Office (EUR-Lex / CELLAR)",
    url: "https://eur-lex.europa.eu",
    gives:
      "The two official texts compared in step 1, word by word, whatever their division into articles and paragraphs.",
    layers: [
      { layer: "proposal", unit: "words in the proposal", words: "proposal_units" },
      { layer: "final_act", unit: "words in the final law", words: "final_units" },
    ],
  },
  {
    id: "amendments",
    name: "Parliament amendments and Members",
    publisher: "Parltrack, compiled from European Parliament records (ODbL licence)",
    url: "https://parltrack.org/dumps",
    gives:
      "Each amendment's original and proposed wording, its tablers, date and committee, and each Member's political group on that date.",
    layers: [
      { layer: "committee_amendments", unit: "committee amendments" },
      { layer: "plenary_amendments", unit: "plenary amendments" },
    ],
  },
  {
    id: "consultation",
    name: "Public consultation submissions",
    publisher: "European Commission, Have Your Say",
    url: "https://ec.europa.eu/info/law/better-regulation/have-your-say",
    gives:
      "Feedback and attached position papers on this law, with publication date and submitter, searched in step 3.",
    layers: [{ layer: "asks", unit: "feedback submissions" }],
  },
  {
    id: "register",
    name: "Organisation identities",
    publisher: "EU Transparency Register (open data)",
    url: "https://transparency-register.europa.eu",
    gives: "Registered names and IDs, so a submission is credited to the right organisation.",
    layers: [{ layer: "actors", unit: "Members and organisations identified" }],
  },
];

const statusText: Record<AtlasLayerStatus, string> = {
  complete: "complete",
  partial: "partial",
  missing: "missing at the source",
  stale: "source no longer updated",
  not_applicable: "not applicable",
  not_collected: "not collected",
};

function coverageLine(
  coverage: readonly AtlasLayerCoverage[],
  layer: AtlasLayer,
  unit: string,
  words: number | null | undefined,
): { text: string; complete: boolean; reason: string | null } {
  const row = coverage.find((item) => item.layer === layer);
  if (row === undefined) {
    return { text: `${unit}: not recorded`, complete: false, reason: null };
  }
  const shown = words === undefined ? row.count : words;
  const amount = shown === null ? "" : `${count.format(shown)} `;
  return {
    text: `${amount}${unit}${row.status === "complete" ? "" : ` (${statusText[row.status]})`}`,
    complete: row.status === "complete",
    reason: row.reason,
  };
}

/** The public sources behind the steps, with what this law's run took from each. */
function Sources({
  coverage,
  counts,
}: {
  coverage: readonly AtlasLayerCoverage[];
  counts: LineageCounts;
}) {
  return (
    <section aria-labelledby="lineage-sources" className="space-y-3">
      <div className="max-w-3xl space-y-1">
        <h4 id="lineage-sources" className="font-serif text-lg text-stone-900">
          Where the data comes from
        </h4>
        <p className="text-sm leading-6 text-stone-600">
          Public records only. Each downloaded file is kept with its address, download time and
          fingerprint, so every number can be traced to the copy it came from.
        </p>
      </div>
      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {SOURCES.map((source) => (
          <li
            key={source.id}
            className="flex flex-col gap-2 rounded-md border border-stone-200 bg-white p-4"
          >
            <p className="font-medium text-stone-900">{source.name}</p>
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-teal-800 underline underline-offset-2"
            >
              {source.publisher}
            </a>
            <p className="text-sm leading-6 text-stone-700">{source.gives}</p>
            <ul className="mt-auto space-y-1 rounded-sm bg-stone-100 px-3 py-2 text-sm">
              {source.layers.map(({ layer, unit, words }) => {
                const line = coverageLine(
                  coverage,
                  layer,
                  unit,
                  words === undefined ? undefined : counts[words],
                );
                return (
                  <li key={layer} className="tabular-nums text-stone-900">
                    {line.text}
                    {!line.complete && line.reason !== null && (
                      <span className="block text-xs leading-5 text-amber-900">{line.reason}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ul>
      <p className="text-xs text-stone-500">
        Not used: meetings with lobbyists, votes, and the Council and trilogue records. The semantic
        matches in step 3 are judged by Jev, a language model run by TypeSafe; it reads these
        sources and adds no data of its own.
      </p>
    </section>
  );
}

function Arrow() {
  return (
    <span aria-hidden="true" className="flex items-center justify-center text-2xl text-stone-400">
      <span className="lg:hidden">↓</span>
      <span className="hidden lg:inline">→</span>
    </span>
  );
}

/**
 * The method in plain words: the four steps from proposal to ranking as a flowchart, each
 * with its rule and this law's result, then what the evidence cannot show. It restates the
 * pipeline's rules (`services/lineage.py`, `origin.py`, `lineage_jev.py`); it computes nothing.
 */
export function LineageMethod({ view }: { view: LineageView }) {
  const steps = stepsFor(view);
  return (
    <section aria-labelledby="lineage-method" className="space-y-6">
      <header className="max-w-3xl space-y-1">
        <h3 id="lineage-method" className="font-serif text-xl text-stone-900">
          How this analysis works
        </h3>
        <p className="text-sm leading-6 text-stone-600">
          It starts from the law as adopted and works backwards, in four steps. Every number is
          counted by code from public records; nobody picks or edits a link by hand.
        </p>
      </header>
      <ol className="grid gap-2 lg:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr]">
        {steps.map((step, index) => (
          <li key={step.id} className="contents">
            {index > 0 && <Arrow />}
            <div className="flex flex-col gap-3 rounded-md border border-stone-200 bg-white p-4 shadow-sm">
              <div className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className="flex size-7 shrink-0 items-center justify-center rounded-full bg-stone-800 text-xs font-semibold text-white"
                >
                  {index + 1}
                </span>
                <h4 className="font-medium text-stone-900">{step.title}</h4>
              </div>
              <p className="text-sm italic text-stone-600">{step.question}</p>
              <ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-stone-700">
                {step.rules.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
              {step.id === "origin" && (
                <p className="flex flex-wrap gap-2 text-xs">
                  <KindBadge kind="verbatim" note="same words" />
                  <KindBadge kind="semantic" note="other words, Jev" />
                </p>
              )}
              <p className="mt-auto rounded-sm bg-stone-100 px-3 py-2 text-sm text-stone-900">
                <span className="text-xs uppercase tracking-wide text-stone-500">
                  In this law:{" "}
                </span>
                <span className="font-medium tabular-nums">{step.result}</span>
              </p>
            </div>
          </li>
        ))}
      </ol>
      <Sources coverage={view.coverage} counts={view.counts} />
      <div className="max-w-3xl rounded-md border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
        <p className="font-medium">What this does not prove</p>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>
            Shared wording is evidence, not authorship: a common draft, a coalition, or the
            Council's own drafting can explain the same words.
          </li>
          <li>
            Meetings, letters and the Council and trilogue negotiations are not in the records, so
            influence through them is not seen.
          </li>
          <li>
            Wording rephrased before adoption is missed, so Parliament's share is a floor, not a
            ceiling.
          </li>
        </ul>
      </div>
    </section>
  );
}
