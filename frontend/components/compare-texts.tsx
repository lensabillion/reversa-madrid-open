"use client";

import { useEffect, useRef, useState } from "react";
import type { ComparisonResult } from "../lib/api";
import { DocumentInput } from "./document-input";
import { EvidenceColumns } from "./evidence-columns";

type Side = "amendment" | "submission";
interface InputText {
  old: string;
  new: string;
}
type Inputs = Record<Side, InputText>;
const labels: Record<Side, string> = {
  amendment: "Amendment",
  submission: "Lobby submission or comment",
};
const sides: Side[] = ["amendment", "submission"];
const textareaStyle =
  "w-full resize-y rounded-sm border border-stone-300 bg-white p-4 font-serif text-base leading-7 text-stone-800 focus-visible:outline-2 focus-visible:outline-teal-700";

function validationMessage(body: unknown): string {
  if (body && typeof body === "object" && "detail" in body && Array.isArray(body.detail)) {
    const messages: string[] = [];
    for (const issue of body.detail) {
      if (issue && typeof issue === "object" && "msg" in issue && typeof issue.msg === "string") {
        messages.push(issue.msg.replace(/^Value error, /, "").slice(0, 300));
      }
    }
    if (messages.length) {
      return [...new Set(messages)].slice(0, 3).join(". ");
    }
  }
  return "The scorer rejected these texts. Check the 12,000-character and 800-token limits.";
}

/** User text stays editable; each edit invalidates both completed and in-flight scores. */
export function CompareTexts() {
  const [inputs, setInputs] = useState<Inputs>({
    amendment: { old: "", new: "" },
    submission: { old: "", new: "" },
  });
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      request.current?.abort();
    },
    [],
  );

  function invalidate() {
    request.current?.abort();
    request.current = null;
    setPending(false);
    setResult(null);
    setError(null);
  }
  function update(side: Side, field: "old" | "new", value: string) {
    invalidate();
    setInputs((current) => ({ ...current, [side]: { ...current[side], [field]: value } }));
  }
  async function compare() {
    invalidate();
    if (sides.some((side) => !inputs[side].old.trim() && !inputs[side].new.trim())) {
      setError("Enter an original or proposed text for each side.");
      return;
    }
    if (
      sides.some((side) =>
        [inputs[side].old, inputs[side].new].some((text) => Array.from(text).length > 12_000),
      )
    ) {
      setError("Use at most 12,000 characters per text.");
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    try {
      const response = await fetch("/api/v1/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          amendment: {
            old: inputs.amendment.old.trim() ? inputs.amendment.old : null,
            new: inputs.amendment.new,
          },
          submission: {
            old: inputs.submission.old.trim() ? inputs.submission.old : null,
            new: inputs.submission.new,
          },
        }),
        signal: controller.signal,
      });
      if (!response.ok) {
        if (response.status === 422) {
          const body: unknown = await response.json();
          throw new Error(validationMessage(body));
        }
        throw new Error(`Comparison failed (${response.status}). Try again.`);
      }
      const score: ComparisonResult = await response.json();
      if (!controller.signal.aborted) {
        setResult(score);
      }
    } catch (failure: unknown) {
      if (!controller.signal.aborted) {
        setError(failure instanceof Error ? failure.message : "Comparison failed. Try again.");
      }
    } finally {
      if (request.current === controller) {
        request.current = null;
        setPending(false);
      }
    }
  }
  return (
    <main id="comparison" className="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-10">
      <h1 className="font-serif text-3xl tracking-tight sm:text-4xl">Compare texts</h1>
      <p className="mt-3 text-sm text-stone-500">
        English · PDF / UTF-8 text files up to 8 MiB · Compare up to 12,000 characters and 800
        tokens per text
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void compare();
        }}
        className="mt-8"
      >
        <div className="grid gap-8 md:grid-cols-2">
          {sides.map((side) => (
            <section key={side} className="min-w-0">
              <label htmlFor={`${side}-text`} className="mb-3 block text-sm font-medium">
                {labels[side]}
              </label>
              <textarea
                id={`${side}-text`}
                required={!inputs[side].old.trim()}
                rows={8}
                value={inputs[side].new}
                onChange={(event) => update(side, "new", event.target.value)}
                className={textareaStyle}
              />
              <p className="mt-2 text-right text-xs tabular-nums text-stone-500">
                {Array.from(inputs[side].new).length.toLocaleString("en")} / 12,000
              </p>
              <DocumentInput
                label={side === "amendment" ? "Amendment file" : "Submission file"}
                currentText={inputs[side].new}
                onUseText={(text) => update(side, "new", text)}
                onLoadStart={invalidate}
              />
              <details className="mt-5 text-sm text-stone-600">
                <summary className="w-fit cursor-pointer">Original text (optional)</summary>
                <label htmlFor={`${side}-original`} className="sr-only">
                  {side === "amendment" ? "Original amendment" : "Original submission"}
                </label>
                <textarea
                  id={`${side}-original`}
                  rows={4}
                  value={inputs[side].old}
                  onChange={(event) => update(side, "old", event.target.value)}
                  className={`mt-3 ${textareaStyle}`}
                />
              </details>
            </section>
          ))}
        </div>
        {(!inputs.amendment.old.trim() || !inputs.submission.old.trim()) && (
          <p className="mt-6 text-xs leading-5 text-stone-500">
            Add both originals to compare edits. Otherwise both proposed texts are compared.
          </p>
        )}
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <button
            type="submit"
            disabled={pending}
            className="rounded-sm bg-teal-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:opacity-50"
          >
            {pending ? "Scoring…" : "Compare"}
          </button>
          {error && (
            <p role="alert" className="max-w-2xl text-sm text-red-800">
              {error}
            </p>
          )}
        </div>
      </form>
      {result && (
        <section aria-label="Comparison result" className="mt-10 border-t border-stone-300 pt-7">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-xs font-medium uppercase tracking-wider text-stone-500">
                {result.mode === "edits" ? "Edit overlap" : "Text overlap"}
              </h2>
              <p className="mt-2 font-mono text-xl tracking-tight text-stone-700">
                {result.score.toFixed(2)}
              </p>
            </div>
            <p className="max-w-md text-xs leading-5 text-stone-500">
              Lexical similarity, not a probability of influence. Paraphrases may be missed.
            </p>
          </div>
          <EvidenceColumns
            amendment={{
              ...inputs.amendment,
              old: inputs.amendment.old.trim() ? inputs.amendment.old : null,
              language: "en",
            }}
            submission={{
              ...inputs.submission,
              old: inputs.submission.old.trim() ? inputs.submission.old : null,
              language: "en",
            }}
            evidence={result.evidence}
            mode={result.mode}
            sourceMetadata={null}
          />
          {result.negation_conflict && (
            <p className="text-sm text-amber-900">Negation differs between these edits.</p>
          )}
          {result.evidence.length === 0 && (
            <p className="text-xs text-stone-500">No shared wording found.</p>
          )}
        </section>
      )}
    </main>
  );
}
