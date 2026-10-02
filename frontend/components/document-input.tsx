"use client";

import { useEffect, useRef, useState } from "react";

interface ExtractedDocument {
  format: "pdf" | "text";
  pages: { page: number; text: string }[];
  warnings: string[];
  character_count: number;
}
interface UsedPage {
  filename: string;
  page: number;
  text: string;
}

/** Keep extraction separate from scoring: the user chooses and reviews a page before using it. */
export function DocumentInput({
  label,
  currentText,
  onUseText,
  onLoadStart,
}: {
  label: string;
  currentText: string;
  onUseText: (text: string) => void;
  onLoadStart: () => void;
}) {
  const [document, setDocument] = useState<ExtractedDocument | null>(null);
  const [filename, setFilename] = useState("");
  const [page, setPage] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [used, setUsed] = useState<UsedPage | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  async function load(file: File) {
    request.current?.abort();
    request.current = null;
    onLoadStart();
    setDocument(null);
    setPage(null);
    setDraft("");
    setError(null);
    setPending(false);
    const extension = file.name.split(".").at(-1)?.toLowerCase();
    if (extension !== "pdf" && extension !== "txt" && extension !== "md") {
      setError("Choose a .pdf, .txt or .md file.");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setError("Files must be no larger than 8 MiB.");
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    try {
      const response = await fetch("/api/v1/documents/extract", {
        method: "POST",
        body: file,
        signal: controller.signal,
        headers: {
          "Content-Type":
            extension === "pdf"
              ? "application/pdf"
              : extension === "md"
                ? "text/markdown"
                : "text/plain",
        },
      });
      if (!response.ok) {
        const body: unknown = await response.json().catch(() => null);
        let message = `Extraction failed (${response.status}).`;
        if (
          body &&
          typeof body === "object" &&
          "detail" in body &&
          body.detail &&
          typeof body.detail === "object" &&
          "message" in body.detail &&
          typeof body.detail.message === "string"
        ) {
          message = body.detail.message.slice(0, 500);
        }
        throw new Error(message);
      }
      const extracted: ExtractedDocument = await response.json();
      if (!controller.signal.aborted) {
        setDocument(extracted);
        setFilename(file.name);
      }
    } catch (failure: unknown) {
      if (!controller.signal.aborted) {
        setError(failure instanceof Error ? failure.message : "Could not extract this document.");
      }
    } finally {
      if (request.current === controller) {
        request.current = null;
        setPending(false);
      }
    }
  }
  const selectedPage = document?.pages.find((item) => item.page === page);
  return (
    <div className="mt-3 text-xs text-stone-600">
      <input
        type="file"
        accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
        aria-label={label}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) {
            void load(file);
          }
        }}
        className="block w-full max-w-full text-xs file:mr-3 file:rounded-sm file:border-0 file:bg-stone-100 file:px-3 file:py-2 file:text-xs file:text-stone-700"
      />
      {pending && (
        <p role="status" className="mt-3">
          Extracting document…
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-red-800">
          {error}
        </p>
      )}
      {used && (
        <p className="mt-2 break-all">
          {used.filename} · p. {used.page}
          {currentText !== used.text ? " · edited" : ""}
        </p>
      )}
      {document && (
        <section aria-label={`${label} preview`} className="mt-4 border-l-2 border-teal-200 pl-4">
          <p className="mb-3 break-all font-medium">
            {filename} · {document.pages.length} {document.pages.length === 1 ? "page" : "pages"}
          </p>
          <label className="block">
            Page
            <select
              aria-label={`${label} page`}
              value={page ?? ""}
              onChange={(event) => {
                const selected = document.pages.find(
                  (item) => item.page === Number(event.target.value),
                );
                setPage(selected?.page ?? null);
                setDraft(selected?.text ?? "");
              }}
              className="ml-3 rounded-sm border border-stone-300 bg-white px-3 py-2"
            >
              <option value="">Choose a page</option>
              {document.pages.map((item) => (
                <option key={item.page} value={item.page}>
                  {item.page}
                </option>
              ))}
            </select>
          </label>
          {document.warnings.map((warning) => (
            <p key={warning} className="mt-3 leading-5 text-amber-900">
              {warning}
            </p>
          ))}
          {selectedPage && (
            <>
              <label className="mt-4 block">
                Review extracted text
                <textarea
                  aria-label={`${label} extracted text`}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  rows={5}
                  className="mt-2 w-full resize-y rounded-sm border border-stone-300 bg-white p-3 font-serif text-sm leading-6 focus-visible:outline-2 focus-visible:outline-teal-700"
                />
              </label>
              <div className="mt-3 flex flex-wrap items-center gap-4">
                <button
                  type="button"
                  disabled={!draft.trim() || Array.from(draft).length > 12_000}
                  onClick={() => {
                    onUseText(draft);
                    setUsed({ filename, page: selectedPage.page, text: selectedPage.text });
                    setDocument(null);
                  }}
                  className="rounded-sm border border-teal-800 px-3 py-2 text-teal-900 disabled:opacity-40"
                >
                  Use page text
                </button>
                <span>{Array.from(draft).length.toLocaleString("en")} / 12,000 characters</span>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}
