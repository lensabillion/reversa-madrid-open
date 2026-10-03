import type { LineageView } from "../lib/lineage-api";
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
      result: `${known(counts.changed_units)} new words`,
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
        "Quotes of other laws are set aside.",
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
