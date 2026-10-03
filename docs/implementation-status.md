# Implementation Status and Handoff

Updated October 3, 2026, 11:55 CEST. Update this file when a capability or its
verification changes. Issue ownership and PR state live in tbd; implementation contracts
live in the [backend README](../backend/README.md). The
[Influence Atlas brief](brief/influence-atlas-challenge-brief.pdf) defines the
competition. The [Atlas explainer](explainer/influence-atlas-primer.md) explains it from
first principles: what changed, the architecture, the data, the models and the plan. The
[technical design](design/influence-atlas-design.md) gives the record contracts and
acceptance tests for the same eight parts. The [consolidated execution plan](plan.md)
(`rev-f090`) settles where those documents and the uploaded
[technical plan](brief/PLAN.md) disagree, and orders the work as acceptance gates.
`attic/` is not an implementation source.

## Objective and Deliverables

The organizers replaced the Challenge 03 brief at kickoff on 3 October 2026. The first
brief (60 supplied amendment–submission pairs and 20 proposals, scored as CSVs against a
hidden answer key) no longer applies. The owner reported the change and asked to re-plan.

The Influence Atlas asks who shapes EU law since 2019, and hands out no data and no
labels. We deliver three things for the live demo at 19:30 Madrid time:

- **A graph the jury explores live:** actor → ask → amendment → final article, every
  edge showing its evidence (the ask's passage, the amendment's change, the final article).
- **A short public report** answering five questions: who, on what topics, towards what,
  how, and what next.
- **An open-source repository** with an open licence that anyone can rerun.

The jury scores 100 points live: real links 25 (three random edges read side by side),
any law 20 (a law named on the spot, shown with no code changes, in minutes), insight 25,
report 15, ambition 15 (coverage since 2019 and a forecast).

Influence (an amendment borrows from an ask) and outcome (the ask reached the final law)
remain different targets. Similar wording alone proves neither.

## Implemented and Evaluated

Everything below was built for the first brief. The third column says what it becomes.

| Capability | Evidence | Becomes, under the Atlas architecture | Limit |
| --- | --- | --- | --- |
| Change comparison (`lexical-delta-v1`) | PRs #10, #19; practice harness: P@20 0.980, recall 0.814, AUC 0.863 on LobbyPlag; per-fold AUC 0.655–0.987 | The first signal of part 4 (verify links) | English, lexical; weak where wording was adapted |
| Practice harness | PR #20 (merged `4185f3b`): organization-grouped folds, 2,000 seeded 30 + 30 draws, 0.27 s on Apple M5 | The practice loop's LobbyPlag check of part 4's precision | One law (GDPR, 2013), mostly verbatim copies; weak negatives |
| Submission command (`make submit`) | PR #19 (merged `b4b5444`, all nine CI checks green): validated `pairs.csv` and evidence JSONL; 60 pairs in 0.16 s | Its validation and comparison path is reused by part 4; the any-law command (`rev-qn6b`) replaces it as the entry point | No CSV deliverable under the Atlas brief. Its two output renames are each atomic but not a transaction (technical design) |
| PDF/text ingestion | PR #11: page-aware extraction with byte, page, text and expansion limits | Part 1 (collect): consultation papers to passages | No OCR or column reconstruction |
| Evidence workspace (frontend) | PRs #12, #13, #17: three-column view of original law, amendment and lobby wording | Part 8: the evidence card the jury reads | Shows supplied or LobbyPlag pairs, not our graph yet |
| LobbyPlag browsing | 4,867 amendment detail records rehearsed; 1,957 candidate links, 172 verified | Comparison only, marked as historical labels | Never an edge in our graph |
| Extraction foundations (data layout, HTTP cache, rate-limited fetcher, per-law manifest, six typed tables, entity resolution, source catalog, probe/fetch CLI) | `make check-backend` on `feat/extraction-foundations` before merging `main`: 174 backend tests, 100% branch coverage (986 statements, 182 branches) | Part 1 (collect): the fetch, cache and table layer under `rev-pjk2` | No response parser for any source: no catalog URL has been hit by a live request from this repository, and parsers wait on probed shapes. No proposal-to-final diff, no amendment PDF parsing, no coverage report |
| Gates | `make check` on `main` at `b4b5444` plus these docs, 3 October 11:07: exit 0; 192 backend tests, 100% branch coverage (996 statements, 214 branches); 37 frontend tests; build; both audits clean | Unchanged | Tests establish behavior, not accuracy |

Data on disk under `data/` (`measured` 2026-10-03): Parltrack `ep_amendments.json.zst`
holds 1,272,091 committee amendment records, 542,314 of them dated 2019–2026 under 1,589
procedure references, streamed in 6 s with the standard library. The Have Your Say and
EUR-Lex folders hold only GDPR samples: the consultation papers and final texts for
2019–2026 are not downloaded yet. That is the first schedule risk.

## Atlas Graph and Outcome Consumers — 3 October 2026

Agent 3 implemented graph projection and descriptive outcome aggregation against the
merged `atlas-1` contracts. `services/atlas_graph.py` builds published actor → request
→ amendment paths and supported request → final article relations, preserving source
spans, joint attribution and coverage. Invalid joins, inexact quotations, inconsistent
chronology and contradictory outcomes fail explicitly. Audit candidates create no
public paths; unknown final outcomes create no realization edge.

`services/atlas_analysis.py` counts every supplied canonical request, including requests
without published links. Full, partial, not-observed and unknown outcomes stay separate
at each stage; the full-win rate is full outcomes divided by assessed requests. Repeated
amendments cannot multiply wins. Coalition rows overlap, so sample totals cannot be
computed by summing actor rows. Known inventory-count mismatches produce coverage gaps.
The invented two-law fixture produces 11 nodes, 9 edges, 2 published origin links and
1 final realization. Its 6 requests have 2 full, 1 partial, 2 not-observed and 1 unknown
final outcome: 2/5 = 0.4 across assessed requests. These are synthetic contract results,
not accuracy or causal claims. The [backend handoff](../backend/README.md#atlas-graph-and-outcome-consumers)
documents interfaces, limitations and the reproducible fixture benchmark.

`make check` passed on 3 October after integrating main through PR #26 (`bdb0c61`):
538 backend tests; 100% coverage (3,349 statements, 844 branches); Ruff and strict
basedpyright; 6/6 research catalogs; 37 frontend tests, Biome, TypeScript and production
build. Backend audit found no known vulnerabilities or adverse statuses in 31 packages;
frontend audit found 0 vulnerabilities. These services are not wired into a real-data
pipeline, API or live explorer yet. Any-law latency, real links and public report
findings remain unverified. Tracking: `rev-i006` and `rev-5yy6`.

## Collect Command (Atlas Part 1) — 3 October 2026

`influence collect <query>` (`make collect LAW='...'`) joins the merged part 1 connectors
into one run for any law (bead `rev-pjk2`, plan gate 1). The query resolves through a
catalog built from Parltrack's dossiers (CELLAR only for an unknown CELEX or COM number;
an unclear title returns its choices). Stages `texts` (CELLAR proposal and final act,
split into provisions), `amendments` (Parltrack committee and plenary amendments, tabling
MEPs) and `asks` (Have Your Say by COM reference, feedback and attachments split into
passages, senders resolved against the register) save through `StageStore`, keyed by
their inputs and a hash of the package source, and a `law` stage writes one `LawRecord`
with ten typed coverage rows. The manifest is published last. Details: the
[backend README](../backend/README.md#collect-command-atlas-part-1).

Verified offline (`measured`, cloud container, Python 3.14.7): 41 tests in
`tests/test_collect.py` on a small world in the real source formats, covering every
coverage status and stop; `make check-backend` passes with 636 tests and 100% branch
coverage (3,947 statements, 994 branches). First real run (`measured` by Agent 2 on
Windows 11, PR #47, `--no-attachments`): the AI Act collected in 39.4 s uncached and
18.5 s cached, with 4,852 committee and 808 plenary amendments, 376 proposal and 712
final-act provisions, 437 asks and 583 actors. Not yet run: a second procedure, and a
run with attachments. `parliament_position`, `meetings` and `votes` stay
`not_collected`; without the Have Your Say index, the consultation is found by a
labelled title search.

Setup (bead `rev-6c1o`): `make setup` streams the four Parltrack dumps and the register
export into `data/raw/` (atomic, with a `<name>.source.json` provenance record each) and
builds `data/catalog/hys-index.jsonl`, so a fresh checkout needs no hand downloads.
Tested offline (`tests/test_setup.py`) and on local files of the real sizes; not yet run
against the real hosts ([backend README](../backend/README.md#setup-command-atlas-part-1-inputs)).

## End to End: Atlas Command, View API and Explorer Page — 3 October 2026

The first end-to-end check (14:00) found the pipeline's parts working alone but not
together: the graph refused every amendment, whose source document no part had
recorded, and no command, route or page joined collection to the explorer. Fixed:

- Amendments cite the Parltrack dump they were read from (a retrieved, hashed
  `SourceDocument`); a tabling MEP missing from the MEP dump keeps an identity.
- `influence atlas <law>` (`make atlas LAW=...`) collects, runs parts 3 to 7 through
  `services/pipeline.py` and writes `data/laws/<slug>/atlas.json`; `GET /api/v1/atlas`
  and `GET /api/v1/atlas/{slug}` serve it ([backend README](../backend/README.md#atlas-command-and-view-api-parts-3-to-8)).
- The explorer page at `/atlas` lists the laws with a view and opens one by `?law=<slug>`
  (the URL `make atlas` prints): graph, evidence, coverage, the view's limitations and
  outcome counts, with explicit loading, empty, not-found and error states
  ([frontend README](../frontend/README.md#atlas-explorer-page)).

Verified offline (`measured`): on the test world with one genuinely matching pair, the
command publishes one `copied` link with exact quotes, the graph has its `ECHOED_BY`
edge, and the API serves the view; `make check-backend` passes with 732 tests and 100%
branch coverage. In headless Chromium, the built frontend and the real backend serving that
view showed the law, its graph and the quoted phrase; a law without a view showed the
backend's 404 detail, and Back returned to the law. **Not verified:** a real law,
timings, and link precision. Ask extraction is a stand-in (one ask per passage,
`passage-v0`) until part 3's extractor exists, so outcome counts count passages. Part 4
now publishes only `copied`-tier links (`rules-2`, PRs #40 and #43); the view's
limitations sentence is built from those constants. Part 3's candidate search is still
the delta query at 5 per amendment, which PR #41 measured at 0.82 recall@5 on LobbyPlag,
against 0.98 for the union of the delta and whole-text queries at about 6.5 candidates;
adopting it is open.

## Architecture Assessment

The Atlas architecture, agreed when the owner merged PR #21, is eight parts plus a
practice loop ([explainer §6](explainer/influence-atlas-primer.md#6-the-architecture)): collect,
resolve actors, find candidates, verify links, trace outcomes, atlas graph, analyse,
publish. It differs from the first design in four ways: we search for candidate pairs
ourselves (part 3); the judge is tuned for the precision of what we show rather than for
a 50/50 test (part 4); the final law is traced for every link (part 5); and actors,
rankings, explanations, the forecast and the report are new (parts 2, 7, 8).
The technical design adds typed records (source document, procedure, actor, ask,
amendment, article version, public position, evidence link, outcome, forecast, run
manifest) and a seven-step delivery sequence with completion tests. The
[consolidated plan](plan.md) compares both with the uploaded technical plan: it keeps that
plan's law resolver, law bundle, degradation modes and audit, and replaces its scraping
routes, hand-set weights and thresholds, fuzzy quote check, short-edit filter,
fractional credit and leave-one-law-out forecast validation, giving the reason for each
([plan §4](plan.md#4-where-they-differ-and-the-choice)).

The implemented dependency direction stays: HTTP routers → typed contracts and services
→ repositories or extraction and scoring functions, so batch commands call the same
logic without HTTP. A vector or graph database is still unnecessary: one law's index fits
in memory; benchmark before adding storage beyond JSON Lines and, if needed, SQLite.

The main risk is no longer interface breadth but data plumbing: until one command turns
a procedure number into verified links with evidence, nothing else scores.

## Decisions

Record every decision here with its status and where its reasoning lives.
Open decisions are not settled until the project owner agrees.

| Decision | Status | Reasoning |
| --- | --- | --- |
| Compete in Challenge 03 | Decided 2026-10-02 for the first brief; the owner asked on 2026-10-03 to re-plan for the Atlas brief | [Research](research/research-2026-10-02-reversa-challenges.md); [Atlas explainer §1](explainer/influence-atlas-primer.md#1-what-changed-this-morning) |
| The Influence Atlas brief replaces the first Challenge 03 brief | Reported by the owner 2026-10-03 | The new brief's rules ("We hand out nothing"), schedule (demos 19:30, no 19:00 inputs) and scoring leave no hidden test |
| Architecture: eight parts plus a practice loop (Atlas) | Decided 2026-10-03: the owner merged PR [#21](https://github.com/lensabillion/reversa-madrid-open/pull/21) at 11:33 | [Atlas explainer §6](explainer/influence-atlas-primer.md#6-the-architecture), [technical design](design/influence-atlas-design.md); supersedes the seven-part design of 2026-10-02 ([first explainer §11](explainer/influence-graph-primer.md#11-proposed-architecture)) |
| Show only links above a precision threshold; keep the rest as unconfirmed, in a separate audit view | Decided 2026-10-03, with the architecture (PR #21) | The jury reads 3 random edges: with precision p, all three pass with probability p³ (0.95 → 0.86, 0.90 → 0.73) |
| Nobody edits links, scores or rankings; people may audit a random sample to measure precision | Decided 2026-10-03, with the architecture (PR #21) |
| Consolidated execution plan: one answer where the uploaded plan, the explainer and the design differ; acceptance gates in order | **Proposed** 2026-10-03; decided when the owner merges the PR that adds it | [docs/plan.md](plan.md), §3 for each choice and its reason; bead `rev-f090` | The first brief's hand-labelling ban no longer exists; AGENTS.md "Data and Challenge Rules" |
| Backend: Python 3.14, FastAPI, uv; Ruff, strict basedpyright, 100% branch coverage | Decided 2026-10-02 | PR [#3](https://github.com/lensabillion/reversa-madrid-open/pull/3) |
| Frontend: Next.js 16.3.6, Tailwind CSS v4, Biome, Vitest | Decided 2026-10-02 | PR [#5](https://github.com/lensabillion/reversa-madrid-open/pull/5); D2 in the first explainer |
| TypeScript 7 rather than 6 | Decided 2026-10-02, by merging #5 and #8 | PR #5: Next.js 16.3.6 type-checks with the project's own `tsc` |
| `next` 16.3.6 inside the 14-day cool-off | Approved 2026-10-02; clears 2026-10-06 | [SUPPLY-CHAIN-SECURITY.md](../SUPPLY-CHAIN-SECURITY.md); follow-up `rev-h455` |
| Project state lives in the repository, not in sessions | Decided 2026-10-02 | AGENTS.md, "Where the Project's State Lives" |
| Parsed tables are JSON Lines, not Parquet | Decided 2026-10-03 | The playbook asks for Parquet; pyarrow is a new dependency the 14-day cool-off and `no-build` policy have not cleared, and JSON Lines is equally safe against delimiters in legal text. The typed row models in `backend/src/influence/extraction/tables.py` are the contract, so the container can change without touching a parser |
| Probe before parse: no parser is written against an unverified response shape | Decided 2026-10-03 | The extraction playbook's own instruction. `python -m influence.extraction probe` records each source's real status, content type and first 200 characters; see the [backend README](../backend/README.md) |
| D3: the earlier prototype in `attic/` | Decided 2026-10-02: not built on | The [influence-architecture skill](../.agents/skills/influence-architecture/SKILL.md) applies this |
| Adopted = the requested wording survives in the final law, labelled automatically | Decided 2026-10-03 (owner, under `rev-e5xh`) | Carries over to part 5 (trace outcomes, `rev-uhpq`) |
| D1: language-model judge | **Local evaluation authorized; no paid API** by the owner, 3 October 2026 | A pinned local DeBERTa NLI model scored 17/24 on a separate synthetic legal diagnostic. Evaluation is authorized; automatic publication is not validated. Raw outputs and labels stay separate. See [calculation handoff](design/calculation-handoff.md), `rev-jaig` and `rev-qs6i`. |
| D4: team split | **Open**; teams may now be 3–4 | [Atlas explainer §12](explainer/influence-atlas-primer.md#12-todays-plan) |
| D5: organizer questions of the first brief | **Superseded**; one question remains: may we use code written before today? | Bead `rev-qvmx` |
| D6: open licence and public repository | **Open**; outward-facing, owner only. Proposed: Apache-2.0 code, ODbL graph data (Parltrack-derived), CC BY 4.0 report | Bead `rev-nzqr`; the repository is private with no licence (`gh`, 2026-10-03) |

## Next Work in Competition Order

The beads below are children of the epic `rev-i2dl` and depend on each other in this
order (`tbd ready` shows what is unblocked). Points are the brief's criteria each one
carries. [Plan §8](plan.md#8-acceptance-gates-in-order) gives each step its completion
test and target time.

1. `rev-pjk2` Part 1 · Collect one law from its procedure number; start the downloads
   for the flagship laws now, in the background (every criterion depends on it).
2. `rev-aapn` Part 3 · Find candidates; `rev-637f` coordinated amendments from Parltrack
   alone (a first insight with no new downloads).
3. `rev-nuk5` Part 4 · Verify links, with `rev-zzur` (threshold), `rev-sbrp` (legal
   polarity) and `rev-jaig` (D1). Real links, 25.
4. `rev-uhpq` Part 5 · Trace outcomes: heard, adopted by Parliament, won.
5. `rev-1vxz` Part 2 · Resolve actors, and `rev-i006` Part 6 · Atlas graph.
6. `rev-qn6b` Part 8 · Any-law command and explorer. Any law, 20.
7. `rev-sn3u` Blind audit of published links: precision with a Wilson interval.
8. `rev-5yy6` Rank; `rev-fod0` Report. Insight, 25; report, 15.
9. `rev-0who` Batch over all 2019+ laws; `rev-104q` Forecast. Ambition, 15.
10. `rev-rg6l` Explain: channels and public statements against asks.
11. `rev-nzqr` D6 licence and public repository, before 19:30; `rev-p61s` rerun from a
    fresh checkout.

Cut lines and the hour-by-hour plan are in
[explainer §12](explainer/influence-atlas-primer.md#12-todays-plan).
Public-source coverage, the any-law runtime and forecast quality are unverified until
those beads report measurements.

The initial extraction foundation had no parsers; PR #26 subsequently added the
source connectors listed in the Agent 1 handoff below. The original playbook sequence was: probe every catalog URL and record the real response shapes, resolve one procedure
identifier into a manifest, split the proposal and final act into units and diff them,
chunk consultation submissions into one ask per passage, parse committee amendment PDFs,
then write the per-law coverage report. Nothing in that sequence should be written before
the step it depends on has a recorded response shape. Create a bead per step.

## Agent 1 Handoff: Data and Integration

The full handoff is [docs/agents/agent-1-handoff.md](agents/agent-1-handoff.md): branches,
what is done and measured, what is unfinished, the gate's state, the next
steps in order and how to run things on the Windows laptop. Its branch and PR states
are historical: PRs #25 and #26 are now merged, through `bdb0c61`. The summary below
preserves the handoff observations; the Agent 3 section above records the newer graph
and analysis consumer work.

- PR [#25](https://github.com/lensabillion/reversa-madrid-open/pull/25) holds the shared
  contracts (`schemas/atlas.py`, schema `atlas-1`) and fixtures; all nine CI checks are
  green; Agents 2 and 3 build against commit `f1525db`. It is now merged.
- Merged PR [#26](https://github.com/lensabillion/reversa-madrid-open/pull/26)
  (`feat/collect-law`) holds the law-query parser, the resumable stage store, and the
  Parltrack, Transparency Register and actor-resolution connectors (each at 100% branch
  coverage), the CELLAR law-text connector, and the Have Your Say connector with passage
  splitting (its real-data check is not reported yet). The backend gate passes at 14:35:
  486 tests, 100% branch coverage (`measured`).
- Not started: the collect service, `influence collect <query>`, the run on real sources
  for the AI Act and its timings. No real-data link, score or graph is produced by a
  collect service yet; Agent 3's graph consumer is verified on synthetic inputs.

## Continuing in Another Chat

Run `tbd prime`, `tbd sync --pull`, and read the relevant bead before claiming it.
Read `AGENTS.md`, the Atlas brief, the Atlas explainer, the technical design, the
consolidated plan, this file and the backend README. Check Git and PR state before
editing; keep one concern per PR and leave beads open until merge. The first brief's work
is merged on `main` (PRs #10–#20), and the Atlas re-plan in #21. Two sessions re-planned concurrently on 3 October in
one checkout (`rev-sz6q` for the explainer, skill, state and beads; `rev-f090` for the
technical design and plan); check `git status` before editing shared files. The first
`docs/plan.md` was written only in a local checkout and never pushed, so a cloud session
rebuilt it from the bead's notes: commit and push before a session ends. Load data and start services using README
commands; never depend on a previous chat's running server, temporary log or browser
state.

## Agent 3 Graph Interface — 3 October 2026

`feat/atlas-explorer` / PR #24 provides a graph-first workspace, source evidence,
loaded-record search and individual topic/procedure-year filters, plus supplied outcome
counts and report presentation. The `atlas-1` adapter consumes PR #25's shared fixtures;
PR #27's candidate retrieval is merged into the branch. Graph selection opens its exact
source comparison; absent or unpublished evidence IDs produce an explicit gap rather
than showing another link. The opening view explains the investigation in plain language.

`make check-frontend` passed: 83 tests across 11 files, Biome, TypeScript and production
build; npm audit reported 0 vulnerabilities. The build included the LOCAL UNCOMMITTED
synthetic `/atlas-preview` route, which is excluded from the PR. Browser inspection
confirmed the graph and selected connection quotations. These are synthetic checks,
not real findings or complete live integration. [Frontend handoff](../frontend/README.md#atlas-components-and-agent-3-handoff).

The backend graph/count services are PR #28 (`rev-i006`, `rev-5yy6`), with all nine CI
checks passing. Presentation is `rev-oodw` and `rev-1jc4`. Agent 3 is not complete:
reproducible report generation (`rev-fod0`), dated position/channel enrichment
(`rev-rg6l`), forecast-record presentation and complete analysis hydration remain.
The evidence adapter currently rejects multiple final outcomes and multi-source or
multi-field columns; expand that representation before integrating such records.
Agent 1 owns shared route/CLI assembly (`rev-qn6b`); Agent 2 owns inference/forecasting.

Completion needs a real bundle of source texts/provenance, resolved actors, all observed
asks, published assessments, outcomes including unmatched/unknown asks, and coverage.
Then rehearse three random published links and the five-minute presentation. No real
any-law, model-quality, large-graph or final mobile-integration claim is made here.

## Consolidated Calculation Development — 3 October 2026

Work under `rev-qs6i` extends the merged Agent 2 assessment/audit services with quoted-law
masking, rarity, local alignment, legal cues, semantic evidence, law-background/mutual
ranks, grouped fitted logistic support and provenance-bound publication gates. The
[calculation handoff](design/calculation-handoff.md) maps each plan requirement to code,
measurements and remaining dependencies. It does not mark all Agent 3 work complete.

The user authorized local model evaluation only, with no paid API. The isolated
[model runtime and generated report](../backend/models/README.md) record pinned Qwen/E5
encoder runs and DeBERTa NLI. With deletion-only proposals retained, BM25 retrieves
157/172 known LobbyPlag matches at 20; Qwen dense retrieves 142 and Qwen fusion 156;
E5 dense retrieves 138 and E5 fusion 157. Retain BM25: no measured retrieval gain.
The local NLI model matches 17/24 intended synthetic legal relations; seven failures
prevent a claim that it can approve reworded links. These synthetic labels are not an
independent legal audit, and LobbyPlag borrowing labels are not entailment labels.

The existing lexical scorer remains the incumbent. Fitted models and cutoffs are
explicit development artifacts until the paired evaluation and independent publication
audit justify adoption. No real 2019+ blind audit or end-to-end collected-law snapshot
has been established by this calculation work. Complete-law source coverage, part 7
spend/trend/forecast calculations and the final public report remain separate tracked
work; see the handoff rather than inferring completion from a working synthetic graph.

Verification of the calculation branch on 3 October, 14:22 CEST: `make check` exited 0;
854 backend tests passed with 100% coverage (4,666 statements, 1,248 branches); strict
basedpyright reported zero errors/warnings; 83 frontend tests passed, production build
passed, six catalogs validated, and backend/frontend vulnerability audits were clean.
The isolated model gate additionally passed strict typing and four tests, with no known
vulnerabilities in its 57-package audit. Generated grouped evaluation reports are in
`backend/evaluation/calculation-qwen.json` and `calculation-e5.json`; their recorded
implementation hashes match the tested source. Baseline mean precision@20 is 0.9801;
fitted deterministic/background is 0.9765, Qwen full-signals/NLI 0.9671 and E5 0.9718.
No fitted replacement is activated. CI status and PR identity remain on the beads.


### Follow-Up Main Review at `2fbb229`

The calculation branch integrates PRs #37–47, including the Atlas command/API (#45),
frontend `/atlas` route (#46), status-quo outcomes, cautious forecast baseline,
calibration/retrieval experiments and the real-data JSON Lines/long-amendment fixes (#47).
The whole gate passed after this integration: 941 backend tests, 100% coverage
(5,310 statements, 1,386 branches), 94 frontend tests, production `/atlas` build and both
audits clean. New calculation audit digests also bind the reused assessor revision.

An initial real AI Act command stopped on missing raw input files. These have now been
prepared from official downloads and existing public dumps with hash/URL provenance.
A real run is in progress; successful live-law output is not yet claimed. A synthetic
check measured five generated asks but only two in the view/ranking input, confirming
`rev-539s`. Runtime publication's independent audit gap is `rev-ffsz`. The initial
frontend 404 (`rev-13x8`) was on `00033b1`; PR #46 adds the route and its browser check
is being repeated against the current backend. Final test findings follow below.
