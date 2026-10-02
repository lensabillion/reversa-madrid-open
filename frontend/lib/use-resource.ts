"use client";

import { useEffect, useState } from "react";

interface Resource<T> {
  url: string | null;
  data: T | null;
  error: string | null;
}

/** Key responses by URL as well as aborting, so superseded requests never replace evidence. */
export function useResource<T>(url: string | null) {
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
        const response = await fetch(requestUrl, {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(
            response.status === 503
              ? "The local dataset is unavailable."
              : `Evidence could not be loaded (${response.status}).`,
          );
        }
        const data: T = await response.json();
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
  }, [url, attempt]);
  const current = resource.url === url;
  return {
    data: current ? resource.data : null,
    error: current ? resource.error : null,
    loading: url !== null && (!current || (resource.data === null && resource.error === null)),
    retry: () => setAttempt((value) => value + 1),
  };
}
