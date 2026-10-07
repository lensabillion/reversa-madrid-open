# influence Explorer

The Next.js web app that shows what the pipeline wrote. It reads the
[backend API](../backend/README.md) through a same-origin proxy (`/api/v1/…`, in
`next.config.ts`) and renders one explorer, `/lineage` (the home page redirects there),
which starts from the final law and traces each adopted phrase to the amendments that
carried it and the submissions that said it first. The backend supplies the lineage records and Member/group credit ordering. The frontend
derives organisation aggregates and display filters from that view in `lib/lineage-insights.ts`.

## Run

Install the pinned toolchains described in [AGENTS.md](../AGENTS.md), build at least one
law with `make lineage LAW='AI Act'` (or point the backend at the committed snapshots with
`INFLUENCE_DATA_ROOT="$PWD/mock-data" make dev-backend`), then run these in separate terminals from the repository
root:

```sh
make dev-backend
make dev-frontend
```

Open `http://localhost:3000`. The browser calls `/api/v1/…`; Next.js proxies those
requests to `http://127.0.0.1:8000`. Set `INFLUENCE_API_URL` before starting or building
Next.js to use another backend address. `make up` runs both in containers (root README).
There is no sample-data fallback: an unavailable service shows an error with Retry.

On a public host, set `INFLUENCE_PUBLIC_URL` to the site's origin (for example
`https://atlas.example.org`) before building, so the link-preview metadata in
`app/layout.tsx` (Open Graph and Twitter card) resolves against it as `metadataBase`. When
it is unset, `metadataBase` is left out. The site icon (`app/icon.svg`), `/robots.txt`
(`app/robots.ts`, every crawler allowed) and the 404 page (`app/not-found.tsx`) need no
setting.

## Code

- `app/lineage/page.tsx`: the route; `app/page.tsx` redirects to it
- `components/lineage-*.tsx`, `lib/lineage*.ts`: the explorer (below)
- `components/view-state.tsx`: the loading, empty and error messages and the retry link style
- `lib/api-client.ts`: `readJson` and `ApiError`, the backend's own explanation of a non-2xx answer; every read revalidates against the API's ETag (`cache: "no-cache"`), so a rewritten view shows at once and an unchanged one is a 304
- `lib/coverage.ts`, `lib/source-span.ts`: the coverage rows and quoted spans the view carries
- `lib/use-resource.ts`: loading, errors, retries and cancellation shared by API consumers
- `next.config.ts`: the same-origin API proxy and the standalone build output

React renders source text as text, never HTML. The first brief's evidence workspace
(`/workspace`) was removed on 6 October 2026 with the routes it called, and the ask-first
`/atlas` page with its `/api/v1/atlas` routes the same day. The Atlas producer and its
offline consumers were retired on 7 October; neither `/atlas` nor `/analysis` is served.

## Verify

`make check-frontend` runs Biome, strict TypeScript, interaction tests, gate probes and a
production build. `make check` includes backend validation and dependency audits. Tests
use synthetic API responses and committed backend fixtures; the running app uses what the
pipeline wrote.

## Lineage Explorer Page

`/lineage` is the explorer: the header's **Lineage explorer** link opens the maintained website. It shows, for each law `make lineage` has built, which wording of the
final act came from which amendments, who tabled them, and which submissions said the same
words, and when. It reads two backend endpoints through the `/api/v1/…` proxy:
`GET /api/v1/lineage` (the law list) and `GET /api/v1/lineage/{slug}` (one `lineage-1`
view; 404 when the law has none).

The selected law lives in the URL (`/lineage?law=2021-0106-COD`). `lib/lineage.ts`
(`prepareLineage`) joins the view into rows: every adopted phrase with its final-act
quotation, the amendments that carry it and the submissions that say it; every tabled
phrase the same way; credits split into groups and holders in the backend's order. A
record that names a phrase or amendment the view lacks rejects the whole view. Phrases are ordered by evidence (an earlier, non-citation submission first,
then any submission, then length) and paged 20 at a time. Each card reads in the brief's
order, left to right: what the submission said, the amendment that carried it, the final
wording. A search box (every word must appear, ignoring case and accents, across the
wording, quotes, Members, organisations and amendment IDs) and three filters (evidence,
political group, committee) narrow the list. Each submission is labelled "Said before the amendments", "Said
after the first amendment", "Order unknown" or "Citation, not a request", straight from the
view's `eligibility`, `precedes` and `is_citation`. Credits are whole (no fractional
credit) and shown as "N of M amendments adopted" with the rate, in the backend's order. A
count the view could not compute reads "unknown", and a view with `status: "unknown"`
shows its reason. Limitations and coverage gaps sit in a disclosure.

The law opens on a **Summary** tab (a funnel from proposal to law, then the five questions,
one line each with "Explore →"); the detail lives in tabs the reader opens on demand: Who, How, Graph,
Evidence, Check 3 links and Method. Everything comes from the same view only
(`lib/lineage-insights.ts`, `lib/lineage-graph.ts`, linear in the view's records):

- **From proposal to law** (`lineageFunnel`, `LineageFunnel`): the proposal's and the final
  act's provisions (from coverage), the final act's words that are not in the proposal, then
  three steps, each with its share as a 100-cell waffle beside the exact "N of M": new words
  traced word for word to an amendment (and in how many phrases), amendments that got wording
  in, and consultation documents that said that wording first, split into documents with a
  word-for-word origin (teal) and documents found only by a reworded Jev match (violet).
  The document numerator counts distinct documents with an earlier, non-citation origin
  for an adopted phrase; tabled-only origins are excluded. Both the method split and named
  organisation detail use that adopted population. A document with both methods counts once
  as word-for-word; an unknown view or uncomputed document counts keep these figures unknown.
  The narrowing card width is the funnel's shape only. A count not computed reads "unknown" and
  draws no waffle.
- **Method** (`components/lineage-method.tsx`): the pipeline in plain words as a four-step
  flowchart (compare the texts, find the amendment, find who said it first, rank and check),
  each step with its rules and this law's result from `counts`; then "Where the data comes
  from", one card per public source (EUR-Lex/CELLAR, Parltrack, Have Your Say, Transparency
  Register) with what this run took from it, read from `coverage` (a partial layer shows its
  reason); then what the evidence does not prove. It restates the backend's rules and computes nothing.
- **The five questions**: WHO and HOW are answered from the view; WHAT and TOWARDS are
  marked "partly" (one law; no policy-direction analysis is available); NEXT is marked
  "not in this view", because no forecast is computed. Nothing is filled in to look complete.
- **Who gets their way: organisations** (`rankOrganisations`): every named organisation whose
  submission says inserted wording, ranked by adopted phrases it said before any amendment
  carried them, then by adopted phrases said later or undated, then tabled ones. A phrase
  counts once per organisation; citations and unnamed submitters are counted apart, never
  named. Searchable, 15 rows until "Show all".
- **How it got there** (`lineageChannels`): adopting amendments by stage, committee and year
  (each amendment once), the share tabled across political groups, and reworded (Jev, `kind: "semantic"`) matches
  apart from word-for-word ones. Only matches dated before the amendment count, and the view
  keeps only those, so no tile repeats that constant 100%.
- **Graph** (`buildLineageGraph`, `sliceGraph`, `components/lineage-graph.tsx`): organisation
  → exact amendment tabler → final-act occurrence. Each saved support ID identifies one
  experimental association. The overview shows the 12 largest nodes per column; focus uses
  support IDs rather than merged phrase IDs. Methods, tabler level, focus and node limit are
  shared with the inspection sample. Legacy snapshots without carrier supports remain
  inspectable in Evidence; their current graph and organisation associations are unavailable.
- **Check three associations** (`visibleClaims`, `drawClaims`): draws up to three of the
  associations with a complete rendered organisation → tabler → final path after method
  filters, focus and node clipping. A coauthored support counts once. Stable support-ID
  ordering and a seeded Fisher–Yates draw make the sample reproducible; the seed and scope
  are displayed, and changing scope clears the draw. Inspection is not an accuracy audit.

- `app/lineage/page.tsx`: the route; a Suspense boundary lets the shell prerender
- `components/lineage-law-browser.tsx`: law selector, URL state, the view, every state
- `components/lineage-insights.tsx`: the five questions, organisations, channels, link check
- `lib/lineage-api.ts`: endpoint types and readers; `lib/lineage.ts`: the adapter;
  `lib/lineage-insights.ts`: rankings, channels, search and the seeded draw

`tests/lineage-adapter.test.ts`, `tests/lineage-insights.test.ts` and
`tests/lineage-page.test.tsx` read
`backend/tests/fixtures/lineage/view.json`, which the backend writes from its offline test
world. Checked once by hand in headless Chromium: the production build against the real
backend serving that view. Not verified: a real law's run.

### Experimental associations

Every loaded law has a visible notice above its tabs: associations have not passed an
independent accuracy audit, and wording matches or model judgments do not prove authorship
or causal influence. Organisation counts and graph headings describe experimental
associations. The owner chose to keep these exploratory records visible (`rev-u2rn`).
Collection completeness is distinct from association accuracy; random inspection is not an
audit. This presentation policy does not change stored records, eligibility or matching.
