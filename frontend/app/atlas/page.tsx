import type { Metadata } from "next";
import { Suspense } from "react";
import { AtlasLawBrowser } from "../../components/atlas-law-browser";

export const metadata: Metadata = {
  title: "Influence · Atlas explorer",
  description: "See whose requests reached the amendments and final text of collected EU laws.",
};

/**
 * The selected law lives in `?law=`, which only the browser knows on this prerendered page.
 * The Suspense boundary lets Next.js prerender the shell and render the explorer on the client.
 */
export default function AtlasPage() {
  return (
    <Suspense
      fallback={
        <p role="status" className="px-5 py-10 text-sm text-stone-500 sm:px-8">
          Loading the Atlas explorer…
        </p>
      }
    >
      <AtlasLawBrowser />
    </Suspense>
  );
}
