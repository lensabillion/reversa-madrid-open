// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import NotFound from "../app/not-found";
import robots from "../app/robots";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.resetModules();
});

/** layout.tsx reads INFLUENCE_PUBLIC_URL when it is first evaluated, so each case re-imports it. */
async function freshMetadata() {
  vi.resetModules();
  const layout = await import("../app/layout");
  return layout.metadata;
}

test("the not-found page names the problem and links back to the explorer", () => {
  render(<NotFound />);
  expect(screen.getByRole("heading", { level: 1, name: "This page does not exist" })).toBeDefined();
  const link = screen.getByRole("link", { name: "Open the lineage explorer" });
  expect(link.getAttribute("href")).toBe("/lineage");
});

test("robots lets every crawler read every page and names no sitemap", () => {
  expect(robots()).toEqual({ rules: { userAgent: "*", allow: "/" } });
});

test("metadata carries the Open Graph and Twitter previews and omits metadataBase when unset", async () => {
  vi.stubEnv("INFLUENCE_PUBLIC_URL", undefined);
  const metadata = await freshMetadata();
  expect(metadata.title).toBe("influence");
  expect(metadata.openGraph).toEqual({
    title: "influence",
    description: metadata.description,
    siteName: "influence",
    type: "website",
    locale: "en",
  });
  expect(metadata.twitter).toEqual({
    card: "summary",
    title: "influence",
    description: metadata.description,
  });
  expect("metadataBase" in metadata).toBe(false);
});

test("metadata sets metadataBase from INFLUENCE_PUBLIC_URL when the host sets it", async () => {
  vi.stubEnv("INFLUENCE_PUBLIC_URL", "https://atlas.example.org");
  const metadata = await freshMetadata();
  expect(metadata.metadataBase).toEqual(new URL("https://atlas.example.org"));
});

test("icon.svg is well-formed XML with an svg root", () => {
  // Vite rewrites `new URL("<asset>", import.meta.url)` into an inlined data: URL, which
  // node:fs cannot read, so the path is built as a string.
  const testsDir = path.dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(path.join(testsDir, "..", "app", "icon.svg"), "utf8");
  const document = new DOMParser().parseFromString(source, "image/svg+xml");
  expect(document.getElementsByTagName("parsererror")).toHaveLength(0);
  expect(document.documentElement.localName).toBe("svg");
  expect(document.documentElement.namespaceURI).toBe("http://www.w3.org/2000/svg");
});
