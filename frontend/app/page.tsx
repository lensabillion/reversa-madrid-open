/** The landing page at `/`: what the project is, in one sentence. */
export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center px-6 py-8">
      <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">Influence Graph</h1>
      <p className="mt-4 text-lg/8 text-pretty text-zinc-700 dark:text-zinc-300">
        Influence Graph scores how likely an EU amendment was written from a lobby submission, maps
        who wins, and predicts which consultation proposals reach the final law.
      </p>
    </main>
  );
}
