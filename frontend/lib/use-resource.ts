"use client";

import { useEffect, useState } from "react";

interface Resource<T> {
  url: string | null;
  data: T | null;
  error: string | null;
}

/** Reads one response; the hook aborts `signal` once the URL changes or the view unmounts. */
export type ResourceReader<T> = (url: string, signal: AbortSignal) => Promise<T>;

/** The evidence API's reader: JSON on success, a short message naming the failure otherwise. */
async function readEvidence<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, cache: "no-store" });
  if (!response.ok) {
    throw new Error(
      response.status === 503
        ? "The local dataset is unavailable."
        : `Evidence could not be loaded (${response.status}).`,
    );
  }
  const data: T = await response.json();
  return data;
}

/**
 * Key responses by URL as well as aborting, so superseded requests never replace evidence.
 * `read` must be a stable, module-level function: a new function on every render reloads.
 */
export function useResource<T>(url: string | null, read: ResourceReader<T> = readEvidence) {
  const [resource, setResource] = useState<Resource<T>>({ url: null, data: null, error: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (url === null) {
      return;
    }
    const requestUrl = url;
    const controller = new AbortController();
    setResource({ url, data: null, error: null });
    async function load() {
      try {
        const data = await read(requestUrl, controller.signal);
        if (!controller.signal.aborted) {
          setResource({ url, data, error: null });
        }
      } catch (error: unknown) {
        if (!controller.signal.aborted) {
          setResource({
            url,
            data: null,
            error: error instanceof Error ? error.message : "Evidence could not be loaded.",
          });
        }
      }
    }
    void load();
    return () => controller.abort();
  }, [url, attempt, read]);
  const current = resource.url === url;
  return {
    data: current ? resource.data : null,
    error: current ? resource.error : null,
    loading: url !== null && (!current || (resource.data === null && resource.error === null)),
    retry: () => setAttempt((value) => value + 1),
  };
}
