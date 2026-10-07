import { afterEach, expect, test, vi } from "vitest";
import { ApiError, readJson } from "../lib/api-client";

function answer(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("every read revalidates with the API instead of trusting a cached copy", async () => {
  const fetchMock = vi.fn(async () => answer({ laws: [] }, 200));
  vi.stubGlobal("fetch", fetchMock);
  const { signal } = new AbortController();

  await expect(readJson("/api/v1/lineage", signal)).resolves.toEqual({ laws: [] });

  expect(fetchMock).toHaveBeenCalledWith("/api/v1/lineage", { signal, cache: "no-cache" });
});

test("a non-2xx answer becomes an ApiError carrying the backend's own detail", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => answer({ detail: "No lineage view for x" }, 404)),
  );

  const read = readJson("/api/v1/lineage/x", new AbortController().signal);

  await expect(read).rejects.toBeInstanceOf(ApiError);
  await expect(read).rejects.toMatchObject({ status: 404, detail: "No lineage view for x" });
});
