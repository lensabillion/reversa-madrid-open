import Link from "next/link";
import { retryStyle } from "../components/view-state";

/**
 * Shown for every URL no route matches (such as the removed /atlas page) and wherever a
 * route calls `notFound()`. A server component: it reads nothing and holds no state.
 */
export default function NotFound() {
  return (
    <div className="min-h-dvh bg-stone-50 text-stone-900">
      <header className="flex h-[76px] items-center justify-between gap-4 border-b border-stone-200 bg-white px-5 sm:px-8">
        <div className="flex items-center gap-4">
          <span className="text-xl font-semibold tracking-tight text-stone-900">influence</span>
          <span className="hidden h-5 w-px bg-stone-300 sm:block" />
          <span className="hidden text-sm text-stone-500 sm:block">Lineage explorer</span>
        </div>
      </header>
      <main className="mx-auto max-w-2xl px-5 py-16 sm:px-8">
        <p className="text-[11px] font-semibold uppercase tracking-[0.13em] text-stone-600">404</p>
        <h1 className="mt-3 font-serif text-3xl text-stone-900">This page does not exist</h1>
        <p className="mt-4 text-stone-600">
          The address may be mistyped, or the page may have been removed. Every law the pipeline has
          traced is listed in the lineage explorer.
        </p>
        <p className="mt-6">
          <Link href="/lineage" className={retryStyle}>
            Open the lineage explorer
          </Link>
        </p>
      </main>
    </div>
  );
}
