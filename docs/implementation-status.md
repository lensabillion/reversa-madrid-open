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
| Gates | `make check` on `main` at `b4b5444` plus these docs, 3 October 11:07: exit 0; 192 backend tests, 100% branch coverage (996 statements, 214 branches); 37 frontend tests; build; both audits clean | Unchanged | Tests establish behavior, not accuracy |

Data on disk under `data/` (`measured` 2026-10-03): Parltrack `ep_amendments.json.zst`
holds 1,272,091 committee amendment records, 542,314 of them dated 2019–2026 under 1,589
procedure references, streamed in 6 s with the standard library. The Have Your Say and
EUR-Lex folders hold only GDPR samples: the consultation papers and final texts for
2019–2026 are not downloaded yet. That is the first schedule risk.

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
([plan §3](plan.md#3-where-they-differ-and-the-choice)).

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
| D3: the earlier prototype in `attic/` | Decided 2026-10-02: not built on | The [influence-architecture skill](../.agents/skills/influence-architecture/SKILL.md) applies this |
| Adopted = the requested wording survives in the final law, labelled automatically | Decided 2026-10-03 (owner, under `rev-e5xh`) | Carries over to part 5 (trace outcomes, `rev-uhpq`) |
| D1: language-model judge (none, local open model, Claude or Jev) | **Open** | Now runs on thousands of candidates, not 60 pairs; bead `rev-jaig`; [Atlas explainer §10](explainer/influence-atlas-primer.md#10-models-from-hugging-face) |
| D4: team split | **Open**; teams may now be 3–4 | [Atlas explainer §12](explainer/influence-atlas-primer.md#12-todays-plan) |
| D5: organizer questions of the first brief | **Superseded**; one question remains: may we use code written before today? | Bead `rev-qvmx` |
| D6: open licence and public repository | **Open**; outward-facing, owner only. Proposed: Apache-2.0 code, ODbL graph data (Parltrack-derived), CC BY 4.0 report | Bead `rev-nzqr`; the repository is private with no licence (`gh`, 2026-10-03) |

## Next Work in Competition Order

The beads below are children of the epic `rev-i2dl` and depend on each other in this
order (`tbd ready` shows what is unblocked). Points are the brief's criteria each one
carries. [Plan §7](plan.md#7-acceptance-gates-in-order) gives each step its completion
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
