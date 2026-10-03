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

## Atlas Components and Agent 3 Handoff

`AtlasExplorer` and `AtlasEvidence` prepare architecture part 8 to display the graph
from part 6. They are reusable components; the application route still uses the
existing evidence workspace until the shared snapshot adapter is implemented.

- `AtlasExplorer` accepts already assessed links and source coverage notes. It filters
  loaded records by law/actor/request text, topic and year, and opens each link's
  evidence. Published links and unconfirmed/contradicted audit candidates have separate
  views.
- `AtlasEvidence` shows the request, original wording, amendment and final wording,
  with source URLs, pages, dates, supplied assessment methods and limitations. Missing
  originals differ from known empty originals; unknown outcomes differ from failures.
  Unicode code-point spans must exactly match their source quote before highlighting.
- `AtlasLinkView` and `AtlasEvidenceProps` are component props, not an API schema.
  The adapter must preserve stable unique link IDs and map pipeline publication and
  outcome decisions without recalculating them. Supply excerpts from their recorded
  source versions and express coverage gaps in `coverageNotes`.

Agent 3 branch: `feat/atlas-explorer`; component bead: `rev-oodw`; broader graph bead:
`rev-i006`. Base: main `0518f17`. Shared schema revision: **pending Agent 1**. Tests use
synthetic examples only; no real influence findings or graph projection are delivered
by these components. No route, lockfile, scorer or shared backend schema is changed.

Integration needs Agent 1's frozen `GraphSnapshot`, source/evidence fixtures and API
route contract, plus Agent 2's publication decisions and outcomes (including unmatched
asks). Agent 1 creates the separate UI integration child of `rev-qn6b`. Graph projection,
ranking denominators, public-position enrichment, report and forecast views remain open.

Verified on 3 October 2026: 46 frontend tests, Biome, TypeScript, production build and
package audit passed. A temporary synthetic preview was inspected at desktop width and
390-pixel mobile width; mobile content width was 390 pixels with no horizontal overflow.
The preview route was removed. These checks verify presentation, not model accuracy,
live data joins, any-law runtime or jury readiness.
