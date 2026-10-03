# Agent 3 Graph Analysis Report and Explorer

Build the public-facing Influence Atlas from pipeline records. Follow
[the Atlas architecture](../explainer/influence-atlas-primer.md#6-the-architecture), [record contracts](../design/influence-atlas-design.md)
and repository AGENTS.md. Own architecture part 6, descriptive analysis in part 7 and
UI/report in part 8. This is a ready-to-dispatch assignment, not already-started work.

## Scope and Ownership

Own typed graph projection, descriptive rankings, dated public-position/channel enrichment,
report rendering and the existing Next.js explorer. Extend `services/demo.py` or a concrete
atlas graph service and existing frontend components/lib/tests. Do not create a second
static frontend. Read the installed Next.js documentation before changing Next.js behavior.

Agent 1 owns shared schemas, actor identities, CLI/API assembly, lockfiles and integration.
Agent 2 owns ask extraction, scoring, outcomes, publication rules and forecast inference.
Consume their outputs; do not duplicate identity matching, scoring or survival inference.
Request shared contract/routes/dependencies through Agent 1. Work in an isolated worktree.

Existing beads: `rev-i006`, UI portion of `rev-qn6b`, `rev-5yy6`, `rev-rg6l`, `rev-fod0`.
Check ownership and pull/read/start/sync before claiming. Agent 2 owns `rev-104q`; your
forecast view renders its records and limitations.

## Start in Parallel

Begin with Agent 1's frozen GraphSnapshot and evidence fixtures. Build graph/UI before
real matching finishes. Fixture tests are consumer-contract tests, not proof of working
live data. Agent 1 owns parent `rev-qn6b` and creates CLI/API and UI child beads before dispatch.
Claim the UI child only; record its ID and file ownership in your handoff.

## Implementation Order

1. Project actor → ask → amendment → final article paths from provided records. Every
   inferred relation retains supporting spans, dates, methods and coverage. Supported
   heard links can appear with unknown final outcomes. Historical labels never become
   our graph edges. Unconfirmed assessments remain in a separate audit view.
2. Extend existing evidence cards with source quotations and legal versions. Add law
   selection/search, progress/coverage, actor/topic/year filters and clear partial states.
   A graph node or edge opens its exact source evidence. Frontend uses Unicode code-point
   offsets via `Array.from`, not raw UTF-16 indices.
3. Compute reproducible distinct-ask counts and observed outcome rates, with denominators,
   partial wins and unknown counts. Consume Agent 2's outcomes for unmatched asks too;
if absent, report incomplete outcome coverage rather than silently dropping those asks.
Duplicate amendments cannot multiply wins. An incomplete
   ask inventory produces a labelled observed-sample ranking, not an all-actor claim.
   Joint asks retain joint attribution. Smoothing/spend comparisons are optional disclosed
   conventions; no causal credit from equal splitting or text similarity.
4. Enrich using public dated statements, meetings and votes with Agent 1's actor mapping.
   TOWARDS compares requests with statements on matching topic/scope/time; HOW describes
   observed channels. Shared wording is not proof of a coalition and meetings do not
   prove transmission. Missing public statements produce an evidence gap.
5. Render a short public report answering WHO, WHAT, TOWARDS, HOW and NEXT, using the
   same snapshot as the explorer. Each finding has a reproducible query, denominator,
   source-backed case and limitation. Consume Agent 2's forecast/scenario records;
   do not invent probabilities or findings while live inputs are absent.

Raw source material is public but redistribution terms still apply. Do not publish whole
PDFs or citizen names by default. Narrative editing may improve prose without changing
computed links/scores/rankings. Release/licence D6 is handled by Agent 1 and the owner.

## Acceptance and Handoff

Test graph joins, duplicate asks, unknown outcomes, quoted evidence, isolated audit
views, denominators and UI partial states. Verify a narrow/mobile layout and usable
evidence navigation. Rankings/report must reproduce from the snapshot; every reported
number maps to a query. No scoring logic belongs in components.

Provide Agent 1 a graph/analysis/report service with no HTTP dependency, frontend views
and route contract requests. Rehearse three random published links with Agent 2's audit
and a five-minute presentation once real records arrive. Report uncovered questions or
missing statement/forecast evidence candidly. Each handoff includes branch/PR, bead IDs,
commands/results, schema revision, fixture versus real-data status and blockers.

UI child bead of `rev-qn6b`, created 3 October: `rev-ifao`. Claim it, not the parent.
Contracts and fixtures: PR #25, branch `feat/atlas-contracts`, commit `f1525db`.
