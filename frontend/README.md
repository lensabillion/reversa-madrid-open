# Influence Atlas Explorer

The Next.js web app that shows what the pipeline wrote. It reads the
[backend API](../backend/README.md) through a same-origin proxy (`/api/v1/…`, in
`next.config.ts`) and renders two explorers: `/lineage` (the home page redirects there),
which starts from the final law and traces each adopted phrase to the amendments that
carried it and the submissions that said it first, and `/atlas`, which shows the Atlas
view that `make atlas` writes. Both are described below. The app scores and ranks nothing
of its own: every link, count and ranking is read from the view the backend wrote.

## Run

Install the pinned toolchains described in [AGENTS.md](../AGENTS.md), build at least one
law with `make lineage LAW='AI Act'` (or point the backend at the committed snapshots with
`INFLUENCE_DATA_ROOT=mock-data`), then run these in separate terminals from the repository
root:

```sh
make dev-backend
make dev-frontend
```

Open `http://localhost:3000`. The browser calls `/api/v1/…`; Next.js proxies those
requests to `http://127.0.0.1:8000`. Set `INFLUENCE_API_URL` before starting or building
Next.js to use another backend address. `make up` runs both in containers (root README).
There is no sample-data fallback: an unavailable service shows an error with Retry.

## Code

- `app/lineage/page.tsx`, `app/atlas/page.tsx`: the two routes; `app/page.tsx` redirects to `/lineage`
- `components/lineage-*.tsx`, `lib/lineage*.ts`: the lineage explorer (below)
- `components/atlas-*.tsx`, `lib/atlas*.ts`: the Atlas explorer (below)
- `components/highlighted-text.tsx`: merges overlapping evidence spans using Unicode code-point offsets
- `lib/use-resource.ts`: loading, errors, retries and cancellation shared by API consumers
- `lib/source-context.ts`: the text shown around a quoted span
- `next.config.ts`: the same-origin API proxy and the standalone build output

React renders source text as text, never HTML. The first brief's evidence workspace
(`/workspace`: the GDPR amendment browser, the text comparison and the PDF upload) was
removed on 6 October 2026 with the routes it called.

## Verify

`make check-frontend` runs Biome, strict TypeScript, interaction tests, gate probes and a
production build. `make check` includes backend validation and dependency audits. Tests
use synthetic API responses and committed backend fixtures; the running app uses what the
pipeline wrote.

## Lineage Explorer Page

`/lineage` is the explorer: the header's **Lineage explorer** link opens it from the
evidence workspace. It shows, for each law `make lineage` has built, which wording of the
final act came from which amendments, who tabled them, and which submissions said the same
words, and when. It reads two backend endpoints through the `/api/v1/…` proxy:
`GET /api/v1/lineage` (the law list) and `GET /api/v1/lineage/{slug}` (one `lineage-1`
view; 404 when the law has none).

The selected law lives in the URL (`/lineage?law=2021-0106-COD`). `lib/lineage.ts`
(`prepareLineage`) joins the view into rows: every adopted phrase with its final-act
quotation, the amendments that carry it and the submissions that say it; every tabled
phrase the same way; credits split into groups and holders in the backend's order. A
record that names a phrase or amendment the view lacks rejects the whole view, as in the
Atlas page. Phrases are ordered by evidence (an earlier, non-citation submission first,
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
  word-for-word origin (teal) and documents found only by a reworded Jev match (violet). The
  narrowing card width is the funnel's shape only. A count not computed reads "unknown" and
  draws no waffle.
- **Method** (`components/lineage-method.tsx`): the pipeline in plain words as a four-step
  flowchart (compare the texts, find the amendment, find who said it first, rank and check),
  each step with its rules and this law's result from `counts`; then "Where the data comes
  from", one card per public source (EUR-Lex/CELLAR, Parltrack, Have Your Say, Transparency
  Register) with what this run took from it, read from `coverage` (a partial layer shows its
  reason); then what the evidence does not prove. It restates the backend's rules and computes nothing.
- **The five questions**: WHO and HOW are answered from the view; WHAT and TOWARDS are
  marked "partly" (one law; direction labels come from `make directions`); NEXT is marked
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
  → who tabled the amendment (political groups, or Members) → final-act provision, drawn
  from adopted wording an organisation said first. The overview shows the 12 largest nodes
  per column; clicking a node or a line keeps only the paths that share its phrases and
  lists their evidence. Teal lines are lexical, dashed violet ones semantic.
- **Check three links at random** (`drawLinks`): the jury's check built in. It draws three
  adopted phrases a submission said first, with a seeded generator whose seed is shown, so a
  draw can be repeated.

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

## Atlas Explorer Page

`/atlas` shows the Atlas view (`make atlas`) for the laws the pipeline has built. No link
leads to it any more; it is reached by its URL. It reads three backend endpoints, through
the same `/api/v1/…` proxy:

| Endpoint | Answer |
| --- | --- |
| `GET /api/v1/atlas` | `{"laws": [...]}`: slug, procedure, title, run and published-link count per law |
| `GET /api/v1/atlas/{slug}` | One law's `atlas-view-1` view: coverage, `atlas-1` bundle, graph snapshot, rankings, limitations, and `modes` (absent in older files, read as none); 404 when the law has no run |
| `GET /api/v1/atlas/{slug}/coordinated` | The law's clusters of near-identical amendments (`backend/src/influence/schemas/coordinated.py`); 404 when the law has no cluster file |

The selected law lives in the URL (`/atlas?law=2021-0106-COD`), so a reload or a shared
link reopens it. The view becomes `AtlasWorkspace` props: the snapshot as the graph,
`atlasLinkViews(bundle)` as the evidence, one sentence per coverage layer that is not
complete, and a compact data notice. For `passage-v0`, the notice visibly states that
counts represent passages rather than distinct requests. The exact method and every
backend limitation remain in a collapsed native disclosure, with bounded scrolling and
long-ID wrapping. Other extraction methods receive a neutral summary. No limitations
being supplied is not presented as proof of complete coverage. Rankings keep the
backend's order; their rows link no sources yet, and every report section shows its
labelled gap, because no report has been generated.

Every state is explicit: loading, no laws built yet (with the `make atlas LAW='…'` command),
no run for the requested law (the backend's 404 detail), and request failures (the
backend's `detail`, with Retry). If the adapter rejects the bundle, for example a quote
that does not match its source text, the page shows the message and nothing else from that
run: it never renders partial or repaired evidence.

Above the workspace, a **law overview** makes any law readable, including one whose run
published no link:

- **Mode labels** (plan §6, for example "Negotiation in progress") as chips under the title.
- With no published link, a sentence says so and points to **Coordinated amendments**,
  which need no consultation request. The workspace still opens on the graph, whose
  **source layer** badges (one per coverage layer, `AtlasSourceLayers`) say why it is empty.

The workspace's fourth view, **Coordinated amendments**, lists near-identical wording tabled
by Members of different groups: the headline "N of M clusters span political groups" with
the compared, too-short and not-comparable counts, then each cluster in the API's order
(25 at a time) with its groups, and per amendment the committee, date, groups, authors,
target provision and the inserted wording quoted exactly (spans joined with " … ").
**Compare side by side** lays one cluster's amendments in columns. The API's limitations
are shown verbatim. The explorer counts and formats; it does not score, rank or reorder,
and it never says who drafted the wording. Its states are loading, no clusters, no cluster
file (unknown, not zero, with `make atlas LAW='<procedure>'`), and an error with Retry.
`coordinatedView` checks every field of the response and rejects the whole file on the
first fault, so a malformed answer shows an error instead of a partial list.

- `components/atlas-coverage.tsx`: source layer badges, the empty-graph reason and mode labels
- `components/atlas-coordinated.tsx`: the coordinated amendments panel and its states
- `lib/atlas-coordinated.ts`: the route's types, boundary check and reader
- `app/atlas/page.tsx`: the route; a Suspense boundary lets the shell prerender
- `components/atlas-law-browser.tsx`: law selector, URL state, view-to-props mapping, states
- `lib/atlas-api.ts`: endpoint types and readers; a non-2xx answer throws `AtlasApiError`

`tests/atlas-page.test.tsx` feeds the page the committed `atlas-1` fixtures through a mocked
`fetch`, with a stand-in for Next.js's search-params hook. Checked once by hand in headless
Chromium: the production build against the real backend serving a view that
`services/pipeline.py` built from the backend's offline test world. The law opened, its
graph and quoted phrase rendered, a law without a view showed the 404 detail, and Back
returned to the law. Not verified: a real law's run. The law overview and the coordinated
amendments panel are covered by `tests/atlas-coverage.test.tsx`,
`tests/atlas-coordinated.test.tsx` and `tests/atlas-page.test.tsx` with a mocked `fetch`.
Checked once by hand in a browser with `next dev` against a stand-in API that served a
synthetic view without links and the AI Act's real cluster file (269 clusters, 0.6 MB): the
badges, modes, headline, side-by-side comparison and the no-cluster-file message rendered.
That check predates merging the overview with the graph view's source layers, which is
covered by the tests only. Not verified: the real backend's two routes together in a browser.

## Atlas Components and Agent 3 Handoff

`AtlasWorkspace` opens on an explanation and a graph: who requested a change, which
amendment matched it, and what appeared in the final law. Separate views provide the
source evidence and descriptive outcome counts. The home route redirects to
`/lineage`; `/atlas` renders `AtlasWorkspace` from the backend (see
[Atlas Explorer Page](#atlas-explorer-page)).
The local `/atlas-preview` route is an uncommitted, explicitly synthetic rehearsal.

- `AtlasGraph` draws supplied snapshot nodes and edges, with selectable connections and
  supporting quotations. A final outcome connects the request to its article; the UI
  does not infer an amendment-to-article causal edge. Missing outcomes add no edge.
- `AtlasExplorer` filters assessed links by law/actor/request text, each individual
  topic and procedure year. Published links and audit candidates have separate views.
- `AtlasEvidence` shows the request, original legal wording, amendment and final text,
  with URLs, pages, dates, assessment methods and limits. Unknown wording differs from
  known empty wording. Exact Unicode code-point quotes are checked before highlighting.
- `lib/atlas.ts` maps schema-validated `atlas-1` records into display props. It checks
  joins, ownership, source spans and source versions;
  it never decides publication or outcomes. Passage-local offsets are normalized.
  It supports all four assessment states, joint actors and multiple law subjects.

The adapter is a typed projection, not a runtime decoder for arbitrary API JSON.
Its four-column evidence view can represent one source field per column and one final
outcome per request. Unsupported multi-field or multi-source evidence and multiple final
outcomes fail explicitly instead of silently dropping records. The integration owner
must extend this presentation before routing such bundles to it. Shared schemas are
owned upstream and are not changed here.

`AtlasAnalysis` presents pipeline-supplied ordering and counts: full, partial,
not-reflected and unknown outcomes. Full wins are shown against assessed requests;
unknowns are excluded from that denominator and retained in total observed coverage.
An all-unknown sample has no rate. Getting a requested outcome does not prove causation.
Report findings need usable citations; a usable URL does not itself establish accuracy.
Absent findings and forecasts remain labelled gaps.

Tracking: `rev-oodw` (explorer/graph display), `rev-1jc4` (analysis presentation),
`rev-i006` (backend graph), `rev-5yy6` (backend aggregation), `rev-qn6b` (live integration).
Shared contracts and synthetic fixtures arrived in PR #25. Agent 2's PR #27 adds
retrieval, which still needs verification and outcome assessment before publication.
Real data, any-law runtime, calibrated precision, spend-adjusted rankings, forecasting
and the generated public report remain separate acceptance gates.
