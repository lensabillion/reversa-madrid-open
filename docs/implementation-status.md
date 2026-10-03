# Implementation Status and Handoff

Updated 3 October 2026, 17:00 CEST. Update this file when a capability or its
verification changes. Issue ownership and PR state live in tbd; implementation contracts
live in the [backend README](../backend/README.md). The
[Influence Atlas brief](brief/influence-atlas-challenge-brief.pdf) defines the
competition. The [Atlas explainer](explainer/influence-atlas-primer.md) explains it from
first principles: what changed, the architecture, the data, the models and the plan. The
[technical design](design/influence-atlas-design.md) gives the record contracts and
acceptance tests for the same eight parts. The [consolidated execution plan](plan.md)
(`rev-f090`, decided and on `main`) settles where those documents and the uploaded
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

**Common names.** `make collect` and `make atlas` accept a law's common name. PR #49 added
the first alias table: seven names (AI Act, AIA, DSA, DMA, CSDDD, CS3D, EHDS), each
resolved against the real Parltrack catalog. Branch `feat/law-aliases` extends it into
`LAW_ALIASES` in `services/law_query.py`: 84 names for 28 procedures, in English, German,
French and Spanish ("GDPR", "KI-Verordnung", "Ley de IA", "Lieferkettengesetz"). Names
compare without case, accents, punctuation, spacing or a surrounding "the". A name is
tried after the procedure, CELEX and COM shapes and before the title search; it stands
for its procedure number, which must be in the dossiers dump, and the command prints the
dossier's title before any stage runs. Two names spelt alike for different procedures,
or a name that is exactly another procedure's title, return the choices. The 77 added
names were checked against public EUR-Lex or Legislative Observatory pages or this
repository's research tables (`verified` against those pages, 3 October); no live CELLAR
check was run and no real dossiers dump was available, so that each added procedure is in
the dump is `assumed` until a real run prints its title.

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

## Coordinated Amendments (Atlas Part 3, Plan Gate 2) — 3 October 2026

`influence coordinated <law>` (`make coordinated LAW=...`, bead `rev-637f`) lists the
amendments of one law whose inserted wording is near-identical and that Members of
different political groups tabled, from the Parltrack amendments and Members alone, and
writes `data/laws/<procedure>/coordinated.json`. Method, parameters and limits: the
[backend README](../backend/README.md#coordinated-amendments-command-part-3).

`measured` on real sources (WSL2, Intel Core Ultra 7 258V, `--no-attachments`, HTTP
cached): the AI Act has 83 clusters spanning groups of 269 (5,660 amendments, 2,967
compared), the Digital Services Act 80 of 508, the Data Act 72 of 173; clustering takes
about 4 s after collect. `make check-backend`'s commands pass with 999 tests and 100%
branch coverage (5,734 statements, 1,472 branches). **Not verified:** the precision of the
clusters (no audit, parameters proposed), and the group of a Member on the tabling date
(the dump's latest group is used). The clusters are not yet in the view or the explorer.

This closes plan gate 2's last open item. Its other two were already met: recall@20 on
LobbyPlag for BM25, dense and fused (PRs #35, #41, #48), and candidates for the AI Act
(PR #50's run: 12,996 candidate pairs). Still open under gate 2's beads: `pipeline.py`
searches the delta query at 5 per amendment (0.82 recall@5 on LobbyPlag) instead of the
union of the delta and whole-text queries (0.98 at about 6.5 candidates, PR #41).

## Channels, Directions, Demo Fixes and Lineage — 3 October 2026, Afternoon

Merged on `main` since the sections above (`9e1049b`):

- **PR #62** (gate 7b minimum, bead `rev-rg6l`): `make channels` (HOW: consultation
  stage, timing against the proposal, tabling Members and groups, co-signed and
  coordinated amendments) and `make directions` (TOWARDS: a rule-based direction per
  amendment, `direction-rules-1`, and per actor through published links only). Details:
  [backend README](../backend/README.md#channels-command-part-7-how). Verified offline
  (`measured` in the PR): `make check-backend` on `cf27ac1`, 1,142 tests, 100% branch
  coverage, with unit, Hypothesis and fixture end-to-end tests. **Not verified:** no real
  law has been run through either command (no counts, no timing); direction labels are
  English-only and not audited against human labels; actor directions stay empty while
  no link is published; public-voice cards are not started; neither file is in
  `atlas.json` or the explorer.
- **PR #67** (gate 6 demo blockers, beads `rev-48sd`, `rev-7lfp`, `rev-539s`): evidence
  windows of 300 code points either side of each quoted span, with a toggle for the full
  source; one badge per source layer on the graph view, and an empty-graph message that
  says whether a layer failed or nothing passed the publication bar; rankings now count
  every ask and actor (untraced asks as `unknown`), and only links that pass the
  chronology check can be an origin. Verified offline (`measured` in the PR): `make check`
  on `c330458`, 1,152 backend and 115 frontend tests, clean audits. **Not verified:** no
  real law in the explorer, rendering of hundreds of ranking rows, and the size of
  `atlas.json` at 29,000 asks. Direct tracing of unlinked asks stays off (about 130 ms per
  ask, over an hour for the AI Act).
- **Lineage PRs #58–#61 and #66**: an outcome-first path that starts from the final act.
  #58 adds the `lineage-1` contracts (`schemas/lineage.py`); #59 and #66 trace runs of 12
  or more words that stand in the final act, are absent from the proposal and were
  inserted by an amendment, back to those amendments, and share each phrase's credit among
  its tablers (`services/lineage.py`; PR #59 reports 3.3 s, 395 adopting amendments and
  434 phrases on the AI Act); #61 finds which submitted documents contain that adopted
  wording, with dates and citations flagged (`services/origin.py`; on the AI Act with
  attachments and a stand-in for the adoption step, 42 matches from 16 organisations, which the author read as mostly the
  Commission's own annex wording quoted back, not lobbyists' asks); #60 adds the human
  review gate (a seeded sample, two readers' labels kept in a separate file, precision
  with a Wilson lower bound). These figures are as reported in the PRs, not re-measured
  here. **Not verified:** no lineage claim is audited, shared wording is not authorship,
  and no `make` target runs the lineage steps yet (a `lineage` command is in progress).

The last real AI Act run of `make atlas` (`rules-3`, below) published **0 links**, so
gate 3 still fails and a blind audit of published links (gate 7) has nothing to sample.

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
| Nobody edits links, scores or rankings; people may audit a random sample to measure precision | Decided 2026-10-03, with the architecture (PR #21) | The first brief's hand-labelling ban no longer exists; AGENTS.md "Data and Challenge Rules" |
| Consolidated execution plan: one answer where the uploaded plan, the explainer and the design differ; acceptance gates in order | Decided 2026-10-03: the plan is on `main` and bead `rev-f090` is closed | [docs/plan.md](plan.md), §3 for each choice and its reason |
| Backend: Python 3.14, FastAPI, uv; Ruff, strict basedpyright, 100% branch coverage | Decided 2026-10-02 | PR [#3](https://github.com/lensabillion/reversa-madrid-open/pull/3) |
| Frontend: Next.js 16.3.6, Tailwind CSS v4, Biome, Vitest | Decided 2026-10-02 | PR [#5](https://github.com/lensabillion/reversa-madrid-open/pull/5); D2 in the first explainer |
| TypeScript 7 rather than 6 | Decided 2026-10-02, by merging #5 and #8 | PR #5: Next.js 16.3.6 type-checks with the project's own `tsc` |
| `next` 16.3.6 inside the 14-day cool-off | Approved 2026-10-02; clears 2026-10-06 | [SUPPLY-CHAIN-SECURITY.md](../SUPPLY-CHAIN-SECURITY.md); follow-up `rev-h455` |
| Project state lives in the repository, not in sessions | Decided 2026-10-02 | AGENTS.md, "Where the Project's State Lives" |
| Parsed tables are JSON Lines, not Parquet | Decided 2026-10-03 | The playbook asks for Parquet; pyarrow is a new dependency the 14-day cool-off and `no-build` policy have not cleared, and JSON Lines is equally safe against delimiters in legal text. The typed row models in `backend/src/influence/extraction/tables.py` are the contract, so the container can change without touching a parser |
| Common-name aliases live in code (`LAW_ALIASES` in `backend/src/influence/services/law_query.py`, started by PR #49 in `collect.py`), not in `data/catalog/aliases.jsonl` as plan §5 proposed | Decided 2026-10-03: PR #53 (`feat/law-aliases`) merged | `data/` is never committed, so a data file would need its own build script before anyone could rerun it; a reviewed table under `backend/src` is versioned with the code that reads it and checked by a test |
| Probe before parse: no parser is written against an unverified response shape | Decided 2026-10-03 | The extraction playbook's own instruction. `python -m influence.extraction probe` records each source's real status, content type and first 200 characters; see the [backend README](../backend/README.md) |
| D3: the earlier prototype in `attic/` | Decided 2026-10-02: not built on | The [influence-architecture skill](../.agents/skills/influence-architecture/SKILL.md) applies this |
| Adopted = the requested wording survives in the final law, labelled automatically | Decided 2026-10-03 (owner, under `rev-e5xh`) | Carries over to part 5 (trace outcomes, `rev-uhpq`) |
| D1: language-model judge | **Local evaluation authorized; no paid API** by the owner, 3 October 2026 | A pinned local DeBERTa NLI model scored 17/24 on a separate synthetic legal diagnostic. Evaluation is authorized; automatic publication is not validated. Raw outputs and labels stay separate. See [calculation handoff](design/calculation-handoff.md), `rev-jaig` and `rev-qs6i`. |
| D4: team split | **Open**; teams may now be 3–4 | [Atlas explainer §12](explainer/influence-atlas-primer.md#12-todays-plan) |
| D5: organizer questions of the first brief | **Superseded**; the remaining question is answered: the organizers allow code written before today (3 October) | Bead `rev-qvmx`, closed |
| No live frontend demo | Decided by the team 2026-10-03 | The explorer stays in the repository; the demo does not depend on it |
| Re-scope gate 7: audit a seeded random sample of unconfirmed prose links to set the prose threshold | **Proposed** 2026-10-03; only the owner decides | Gate 3 needs a threshold that only an audit can give; the last real AI Act run (`rules-3`) published 0 links, so a blind audit of published links has nothing to sample. [Plan §8](plan.md#8-acceptance-gates-in-order) |
| D6: open licence and public repository | **Open**; outward-facing, owner only. Proposed: Apache-2.0 code, ODbL graph data (Parltrack-derived), CC BY 4.0 report | Bead `rev-nzqr`; the repository is private with no licence (`gh`, 2026-10-03) |

## Next Work in Competition Order

As of 17:00 on 3 October; code freeze 18:30, demos 19:30. Beads are children of the epic
`rev-i2dl`; `tbd ready` shows what is unblocked, and the beads, not this list, hold
ownership. [Plan §8](plan.md#8-acceptance-gates-in-order) gives each gate's test.

Done or merged: gate 1's collection (the AI Act with attachments; the Digital Services
Act and Data Act without), gate 2 (candidates and coordinated amendments), the `make
atlas` command and view API, the gate 7b commands (`make channels`, `make directions`, PR #62), the gate 6 demo fixes (PR #67) and
the lineage steps (PRs #58–#61, #66).

1. **Real links (gates 3 and 7).** `rules-3` publishes 0 AI Act links. The **Proposed**
   gate 7 re-scope (a seeded audit of unconfirmed prose links to set the prose threshold)
   needs the owner's decision before anyone labels (`rev-nuk5`, `rev-zzur`, `rev-sn3u`).
   Audit labels stay apart from model output.
2. **Lineage command.** Join the merged lineage steps into one command and run it on the
   AI Act (in progress in another session); no lineage claim is shown before PR #60's
   review gate passes.
3. **Real runs of gate 7b.** `make channels LAW='AI Act'` and `make directions LAW='AI
   Act'` have never run on a real law (`rev-rg6l`); record counts and timings.
4. **Report** (`rev-fod0`, `rev-5yy6`): every number from a recorded command output; text
   until 18:30.
5. **Release** (gate 11): D6 licence and public repository, owner only (`rev-nzqr`); a
   rerun from a fresh checkout with `make setup && make atlas LAW='AI Act'` (`rev-p61s`).
6. **Demo** without the live frontend (decided): the five-minute script against command
   outputs.

Cut for today unless time remains: the batch over all 2019+ laws (`rev-0who`), the
forecast (`rev-104q`) and gate 10's full explanation. Public-source coverage, the uncached
any-law runtime and forecast quality remain unverified.

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

## Historical Gate 3 Check on `2fbb229` — 3 October 2026

Gate 3 in `docs/plan.md` is **not passed**. Main `2fbb229` plus the bounded-ask fix
`104e462` can build a real AI Act view from the completed collection, but publishes only
**2 links**, below the required 20. Only those two can be read; the requested random
sample of ten cannot be drawn. This check is separate from Gate 7's later two-reader,
40-link blind audit. No scores, links or thresholds were edited to meet the target.

The public collection contains 437 feedback records (133 roadmap and 304 proposal),
352 downloaded attachments, 29,061 passages, 5,660 amendments (4,852 committee and
808 plenary), and 1,088 articles (376 proposal and 712 final-act). Missing/extraction
failures remain explicit, and consultation discovery used the labelled title fallback
because the initiative index was absent. Official input URL/hash provenance is retained
under ignored `data/raw/provenance/`. This is one law, not verified coverage since 2019.

The refreshed full CLI failed after 459.815 seconds: five table-of-contents passages in
one attachment exceeded the scorer's 800-token bound despite having fewer than 120
whitespace words. `rev-g2bi` now checks each parsed ask against the existing `TextChange`
contract before retrieval, preserves original source records, and reports excluded IDs
and reasons. Direct assessment returns `insufficient_evidence` for unsupported asks.
It does not truncate text or change valid scores or publication thresholds.

A measured rebuild from the completed collection succeeded in **249.318 seconds** on
an Apple M5 MacBook Air with 24 GB RAM: retrieval 221.605 seconds for 28,229 candidates,
assessment 15.945 seconds, and outcome tracing 11.235 seconds. This cached service-level
rebuild is not a fresh end-to-end CLI rerun. Collection run `20261003T123800Z` and the
rebuild's separate source fingerprint are recorded in
`data/laws/2021-0106-COD/gate3-build-timing-1791032235984379000.json`.
The view contains 2 published links, 646 unconfirmed links, 11,357 contradicted links,
and a graph of 7 nodes and 6 edges; other insufficient candidates are omitted by the
existing view contract.

`gate3-audit-seed0.json` beside that view records zero structural errors across 27
published-link spans, 12 associated outcome spans, and 29 graph-edge spans checked
against original source text. Four link source citations and two outcome source URLs
are present. There are **zero final-act evidence spans for the published links**; their
absence is not successful outcome verification. Seed zero selects both available links.

Reading both links found the same AI definition matched to ITRE amendment 270. Philips'
surrounding text attributes the definition to the AI High-Level Expert Group; Novartis'
passage is a glossary definition. These are exact wording associations, not evidence of
submission-specific origin. This agent plausibility review is not an independent human
precision audit and is never fed back as hidden labels or edited scores.

Remaining Gate 3 blockers include prose-aware, background-aware verification and a
freshly evaluated threshold (`rev-nuk5`, `rev-zzur`), plus legal polarity (`rev-sbrp`):
a reproduced permission-versus-obligation example is published at support 0.7843 by
`rules-2`. The existing 0.75 cutoff is traceable to `evaluation/link-calibration.json`,
but its held-out Wilson lower bound is 0.8583, not the 0.90 floor claimed in a source
comment (`rev-ffsz`). Local-model evaluation in PR #48 does not activate a replacement
runtime or establish reworded-link precision. Gate 3 remains open.

The bounds-fix branch passed `make check`: 751 backend tests with 100% branch coverage
(4,780 statements and 1,182 branches), 94 frontend tests across 12 files, production
build, strict types, Ruff/Biome, six catalogs, and clean backend/frontend dependency
audits. A deterministic punctuation-only outcome regression also makes an existing
coverage branch independent of chance-based property-test generation.


## Gate 3 Follow-Up on Main `086d42a` — 3 October 2026

Main merged PR #48 (calculation/model evaluation), #49 (real-data collection fixes),
#50 (prose-aware assessment), and #51 (reproducible setup). PR #52 integrates that main
with the bounded-ask fix at `cecb869`. The preceding two-link run is historical: the new
`rules-3` assessor keeps prose matches unconfirmed by default, including shared boilerplate.
No `publish_prose` override is enabled. The same permission/obligation probe is now
unconfirmed at support 0.9167; explicitly enabling prose publication would publish it
without detecting the modal mismatch. The guard prevents default publication but does
not establish legal-meaning accuracy. Prose thresholds and reworded-link validation
remain open (`rev-nuk5`, `rev-sbrp`, `rev-zzur`, `rev-jaig`).

The integrated `make check` passed: 987 backend tests in 15.59 seconds, 100% coverage
(5,627 statements, 1,462 branches), 94 frontend tests in 12 files, six catalogs, strict
types, lint/format, production build and clean audits. All nine remote CI checks passed
at `cecb869`. This confirms engineering checks, not Gate 3 acceptance.

Browser checks on the earlier populated snapshot verified both graph-to-evidence paths,
correct source URLs and highlight counts, with no JavaScript errors. They also found
that displaying an entire long PDF defeats side-by-side reading: the first Novartis
highlight was 46,768 pixels down, where the neighboring columns were blank (`rev-48sd`).
Ranking rows supply no usable source anchors (`rev-1wb7`), and the initial graph should
show source coverage more clearly (`rev-7lfp`). These UI issues are tracked separately
from scoring and have not been fixed by PR #52.

The actual `influence atlas '2021/0106(COD)' --data-root <data>` command then completed
with **exit 0 in 310.134 seconds (5 minutes 10 seconds)**, using verified TLS and the
existing public download cache, without `--refresh` or prose-publication overrides.
Collection took 52.9 seconds, retrieval 212.381 seconds (28,229 candidate pairs),
assessment 29.392 seconds, and outcome tracing 15.010 seconds. The only network attempt
was one feedback-publication request returning HTTP 400; usable downloads were reused.
That missing publication remains in typed coverage. This is a successful full CLI run
with cached public inputs, not an uncached download benchmark or second-law rehearsal.

The resulting `rules-3` view has **0 published, 859 unconfirmed and 82 contradicted
links**, with 27,288 insufficient candidates omitted from the view. The published graph
has one law node and zero edges. **Gate 3 still fails**: there are no published links
against the required 20, and no published sample of ten can be read or checked. A check
of zero published spans is unavailable, not a passing evidence audit. The output follows
the merged policy of withholding unvalidated prose findings.

Run ID: `20261003T130918Z`; view SHA-256:
`ec377825c4c2110cfdb2a76efd82188bc80987419a7d927f17877542ac909fde`.
Diagnostic wrappers recorded phase times and fetch counts without changing algorithms;
the source fingerprint and assessor/pipeline/matcher hashes were captured before the run.
Artifacts remain under ignored `data/laws/2021-0106-COD/`; earlier view/audit artifacts
are preserved separately under `gate3-runs/rules-2-0741e0e3d9fb/`.

## Part 4 Inputs: Ask Direction and Proposal Masking (`rules-4`) — 3 October 2026

Two inputs part 4's rules were written for never reached them on the live atlas path
(`rev-jesy`, `rev-805l`). Asks carried no direction, so the same-direction tier and the
opposite-direction contradiction never ran. `services/masking.py` existed, but only
`services/calculation.py` called it (it is off the live path), so prose could match an
amendment on wording that both took from the proposal. The assessor is now `rules-4`.

- **Direction.** `asks_from_passages` records `assessment.requested_direction`: a quoted
  instruction's change, read by `amendment_direction`, the cue rule the calibration applied
  to LobbyPlag's submissions. Prose keeps `unknown`, and every prose link says its direction
  checks did not run. On LobbyPlag's 272 labelled pairs, the rule finds no opposed pair at
  the copied tier. Across all pairs it marks 2 positives and 5 weak negatives opposed, and
  the same direction in 72 positives and 10 weak negatives. On the AI Act it changes no
  verdict: 29,055 of 29,061 asks are prose, and the 6 quoted instructions hold no
  obligation cue (for example "AI" to "electricity"). A measured prose reader is `rev-0vi1`.
- **Masking.** `QuotedLaw` indexes the proposal's provisions once per law (385 provisions,
  236,809 characters, 12 ms on an Apple M5). Part 4 masks 8-word quotations out of prose
  before shared phrases are found, with a break word at each gap so no run bridges it.
  Evidence offsets stay on the original text. A law without proposal text says so in its
  view.

Same collected run (`20261003T144014Z`), same 28,229 candidates (byte-identical), before
on `main` `8c50f35` and after on this branch:

| Verdict | `rules-3` | `rules-4` |
| --- | ---: | ---: |
| Published | 0 | 0 |
| Unconfirmed, copied tier | 188 | 42 |
| Unconfirmed, reworded tier | 671 | 252 |
| Contradicted | 82 | 36 |
| Shown in the view | 941 | 330 |

Masking removed proposal wording from 13,667 verdicts (48%). Five removed copied-tier
matches (seed 0 of 138) were all proposal wording that the amendment reuses or moves. 83
of the 138 come from amendments whose original wording is unknown, so their whole text
counted as inserted. That is an agent reading, not an audit. All 36 remaining
contradictions come from the sentence-level negation check. Assessment took 29.2 s on
cached candidates against 31.3 s before (single runs; masking all asks costs 0.62 s).
**Gate 3 is still open**: no link is published. The audit view now holds 330 instead of
941 candidates, with the proposal-quotation matches removed. Masking before BM25 is
`rev-yfc0`. Ligatures extracted as U+0000 in 144 passages are `rev-obw8`.

## Frontend Coverage Notice — 3 October 2026

`rev-jc78` fixes the oversized diagnostic wall in the Atlas header (part 8). The visible
notice now explains passage-based counts in one sentence. A native collapsed disclosure
retains the exact method and every supplied limitation; its content scrolls within a
bounded area and long record IDs wrap. Future extraction methods receive neutral wording,
and an empty limitations list does not imply that all data were processed. Scoring,
exclusions, API records and graph publication are unchanged.

The corrected preview at `http://localhost:3015/atlas?law=2021-0106-COD` uses the same
real backend as the previous page. Browser inspection confirms the short notice and
collapsed details above the graph navigation. The existing saved AI Act run still reports
five excluded passages and nine unsearchable amendments; this UI change preserves those
facts instead of presenting raw diagnostics as the main page content. `make check` passed:
1,150 backend tests with 100% branch coverage, 96 frontend tests, production build,
and both dependency audits. Browser expansion and collapse preserved all diagnostics.
PR CI is recorded on the bead.
