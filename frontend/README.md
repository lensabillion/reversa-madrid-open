# Evidence Workspace

The light workspace reads the [backend API](../backend/README.md). Search amendments,
compare a lobby proposal with an amendment, and inspect each amendment's recorded sources.
Historical verification and lexical similarity remain separate; neither proves causation
or adoption.

Evidence appears in three columns, with a short explanation under each heading:

| Column | Meaning |
| --- | --- |
| **Before the amendment** | The draft wording the lawmaker wants to change; this is not a final adopted law. |
| **Lawmaker's proposal** | The wording the lawmaker proposes instead. |
| **Lobby's proposal** | The wording the organization requested; its name, document and page identify the source. |

Desktop shows the three passages together; narrow screens stack them in that order.
The score is secondary to the wording. Supplied-text comparisons use the same labels;
they do not invent an organization or document reference for pasted text.

In edit comparisons, teal marks shared added wording and amber strike-through marks
shared removed wording. The lobby column also offers **Original lobby wording**, which
opens automatically for deletion-only evidence. Whole-passage comparisons label marks
as shared wording, because an edit cannot be inferred without both originals. Missing
originals are explicit; a known empty original is distinct from unavailable text.
Highlights identify matching evidence, not every edit. Full supplied excerpts remain
available; the view does not infer aligned paragraphs or shorten the source text.

**Explore** uses the historical dataset. **Compare texts** accepts your own amendment
and lobby submission or consultation comment. Paste text or upload a searchable PDF,
UTF-8 `.txt`, or `.md` file. Choose a page, review the extraction, and use its text.
Edits to extracted wording are marked. Files are limited to 8 MiB; comparison text is
limited to 12,000 characters and 800 tokens per side. Scanned PDFs need OCR, which this
demo does not provide.

Original wording is optional. With both originals, the backend compares edits; otherwise
it compares full passages and labels the result **Text overlap**. Unknown originals are
sent as `null`, never guessed to be empty. With both originals supplied, an empty proposed
text can represent a deletion. Results are lexical similarity, not influence or adoption
probabilities. Changing an input clears its old result.

## Run

Install the pinned toolchains described in [AGENTS.md](../AGENTS.md), download the public
data using the backend guide, then run these in separate terminals from the repository root:

```sh
make dev-backend
make dev-frontend
```

Open `http://localhost:3000`. Search `ITRE 616` for the Amazon example. The browser calls
`/api/v1/…`; Next.js proxies those requests to `http://127.0.0.1:8000`. Set
`INFLUENCE_API_URL` before starting or building Next.js to use another backend address.
There is no sample-data fallback: unavailable services show an error with Retry.

## Code

- `components/workspace.tsx`: search, pagination, selection and source comparison
- `components/compare-texts.tsx`: user inputs, comparison request and result evidence
- `components/evidence-columns.tsx`: shared original/amendment/submission layout and evidence routing
- `components/document-input.tsx`: extraction, page review and provenance for uploaded text
- `components/highlighted-text.tsx`: merges overlapping spans using Unicode code-point offsets
- `lib/use-resource.ts`: loading, errors, retries and cancellation shared by API consumers
- `lib/api.ts`: the backend response shapes consumed by the interface
- `next.config.ts`: same-origin API proxy

React renders source text as text, never HTML. Switching amendments clears prior evidence;
aborted requests cannot replace the current selection. Narrow screens stack panels.
Uploads and comparisons use `/api/v1/documents/extract` and `/api/v1/compare`; the backend
owns both extraction and scoring, so a future batch command can reuse them.

## Verify

`make check-frontend` runs Biome, strict TypeScript, interaction tests, gate probes and a
production build. `make check` includes backend validation and dependency audits. Tests
use synthetic API responses; the running demo uses the downloaded public data.

October 2 validation: combined `make check` exited 0 with 106 backend tests (100% branch
coverage), 38 frontend tests, a successful production build and clean dependency audits.
Independent review regressions cover deletion-only results exposing original evidence
and non-JSON upload errors. In the production browser, the
organizers' PDF uploaded as 16 pages; selecting page 12 and comparing it with a supplied
excerpt returned highlighted evidence and retained page provenance. This is a transport
check, not a model-quality evaluation. ITRE 616 displayed Amazon's historical verified
link separately from its 0.71 lexical score. No browser warnings/errors were observed;
exhaustive device and screen-reader testing remains unverified. For the three-column
follow-up, production-browser checks measured equal 270-pixel columns at a 1280-pixel
viewport; at 390 pixels they stacked in order and document width stayed 390 pixels.
A live deletion-only comparison displayed removed wording in the starting draft and the
automatically opened Original lobby wording disclosure. Independent source review found
no remaining issue in offset routing, missing-data handling or deletion visibility.

Work and review evidence are tracked in **rev-oze0** and **rev-8mwe**; extraction is
**rev-i2v8**. The foundation is **rev-ic1h** (merged PR #10). See
[implementation status](../docs/implementation-status.md) for the architecture assessment
and remaining competition work.
The three-column comparison follow-up is tracked in **rev-q24c**.
The role-label clarification is tracked in **rev-foxs**.
Its full `make check` also passes 106 backend and 38 frontend tests, build and audits.
Browser inspection confirmed the three explanatory captions and Amazon's filename/page
inside its own column. Model accuracy is unchanged by this display clarification.

## Atlas Explorer Page

`/atlas` shows the Atlas for the laws the pipeline has built; the header's **Influence
Atlas** link opens it from the evidence workspace. It reads three backend endpoints, through
the same `/api/v1/…` proxy:

| Endpoint | Answer |
| --- | --- |
| `GET /api/v1/atlas` | `{"laws": [...]}`: slug, procedure, title, run and published-link count per law |
| `GET /api/v1/atlas/{slug}` | One law's `atlas-view-1` view: coverage, `atlas-1` bundle, graph snapshot, rankings, limitations, and `modes` (absent in older files, read as none); 404 when the law has no run |
| `GET /api/v1/atlas/{slug}/coordinated` | The law's clusters of near-identical amendments (`backend/src/influence/schemas/coordinated.py`); 404 when the law has no cluster file |

The selected law lives in the URL (`/atlas?law=2021-0106-COD`), so a reload or a shared
link reopens it. The view becomes `AtlasWorkspace` props: the snapshot as the graph,
`atlasLinkViews(bundle)` as the evidence, one sentence per coverage layer that is not
complete, and the limitations plus the ask method as the data notice. Rankings keep the
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
- **Layer badges**: one per coverage layer, with its status, its count and, unless the layer
  is complete, the pipeline's reason. A count the run did not make reads "not counted",
  never 0.
- With no published link, a sentence says that the graph is empty, that this is not a finding
  that nobody shaped the law, and how many unconfirmed or contradicted candidates sit under
  **Read the evidence → Audit candidates**. The workspace then opens on the coordinated
  amendments instead of the empty graph.

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

- `components/atlas-coverage.tsx`: layer badges and mode labels
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
`tests/atlas-coordinated.test.tsx` and `tests/atlas-page.test.tsx` with a mocked `fetch`
only: they have not been opened in a browser against the real backend.

## Atlas Components and Agent 3 Handoff

`AtlasWorkspace` opens on an explanation and a graph: who requested a change, which
amendment matched it, and what appeared in the final law. Separate views provide the
source evidence and descriptive outcome counts. The home route still uses the earlier
evidence workspace; `/atlas` renders `AtlasWorkspace` from the backend (see
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
