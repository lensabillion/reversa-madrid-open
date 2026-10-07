import type { Metadata } from "next";
import { Suspense } from "react";
import { LineageLawBrowser } from "../../components/lineage-law-browser";

export const metadata: Metadata = {
  title: "influence · Lineage explorer",
  description:
    "Explore experimental wording associations between EU laws, amendments, their tablers and consultation submissions.",
};

/**
 * The selected law lives in `?law=`, which only the browser knows on this prerendered page.
 * The Suspense boundary lets Next.js prerender the shell and render the explorer on the client.
 */
export default function LineagePage() {
  return (
    <Suspense
      fallback={
        <p role="status" className="px-5 py-10 text-sm text-stone-500 sm:px-8">
          Loading the lineage explorer…
        </p>
      }
    >
      <LineageLawBrowser />
    </Suspense>
  );
}
