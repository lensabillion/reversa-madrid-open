# Agent 1 Data and Integration

Implement the data foundation and integrate the Influence Atlas. Follow
[the Atlas architecture](../explainer/influence-atlas-primer.md#6-the-architecture), [record contracts](../design/influence-atlas-design.md)
and repository AGENTS.md. Architecture parts 1 and 2, plus the command/release portion
of part 8. This file is a ready-to-dispatch assignment; it does not claim work has started.

## Scope and Ownership

Own the generic law resolver, public-source collection, normalization, actor resolution,
run manifests/cache receipts and CLI orchestration. Extend `backend/src/influence/`;
do not create a second backend. Reuse bounded PDF extraction and the existing scorer's
edit extraction. Own source-specific repository modules and collection/actor tests.

You are the integration owner for shared schema `schemas/atlas.py`, `cli.py`, `api.py`,
thin atlas routers, Makefile, dependency lockfiles, README and implementation status.
Agents 2 and 3 request changes to these files through you. Coordinate dependency requests
sequentially under the repository supply-chain rules. Never change another agent's files
or switch its worktree branch.

Existing beads: `rev-pjk2` collection, `rev-1vxz` actors, CLI portion of `rev-qn6b`,
`rev-0who` coverage/batch, `rev-p61s` reproduction and `rev-nzqr` release preparation.
Check current claims before claiming or dispatching work; follow pull/read/start/sync.
You own parent `rev-qn6b`. Before dispatch, create separate CLI/API and UI child beads;
Agent 3 claims the UI child, not the parent. Record the child IDs in both handoffs so
one bead never has competing delegates.

## First Handoff Before Other Agents Build

Create a small shared-contract PR and fixtures under `backend/tests/fixtures/atlas/`.
Freeze the minimal LawRecord, SourceDocument, SourceSpan, Actor, Ask, Amendment,
Candidate, LinkAssessment, ArticleVersion, PublicPosition, Outcome, Forecast/scenario,
GraphSnapshot and RunManifest contracts. Include
schema versions, canonical IDs, original Unicode code-point offsets, null/unknown states
and coverage counts. Ask extraction belongs to Agent 2; you define its input/output shape.

Provide fixtures for a supported copy, opposite request, short shall/may edit, ambiguous
actor, missing date, missing final act and partial outcome. Fixtures enable parallel
consumer work but are not accuracy evidence. Tell both consumers which revision to use.

## Build the Data Path

1. Resolve procedure, title, CELEX or COM through a reusable catalog. Ambiguous titles
   return choices. Verify cross-source identifiers; do not silently accept fuzzy joins.
2. Collect the law bundle: metadata, proposal, available Parliament position/final act,
   amendments, dated feedback/attachments, and source actor IDs. Stream/filter Parltrack
   with stdlib zstd. Use documented HYS/CELLAR routes with contract tests. Stale dumps
   remain stale even when downloaded today; Parliament metadata does not itself supply
   parsed amendment text.
3. Preserve raw public bytes under ignored `data/`, extracted text and exact provenance.
   Unavailable sources produce explicit coverage gaps. Unknown dates stay unknown.
4. Resolve actors by source/register IDs; name matches propose aliases, with uncertainty.
   Missing register records do not erase a quoted ask. Citizens are not named in output.
5. Add resumable stage receipts and fresh run directories. Cache reuse depends on inputs,
   code/config/model revision. Publish the completion manifest only after export validation.
6. Wire Agents 2/3 services into the existing `influence` CLI and thin API adapters. Only
   one service implementation per job; UI and CLI consume the same snapshot.

Proposed first law: AI Act. Also resolve DSA and an unseen procedure using the same code.
Optional meetings/public statements are Agent 3's enrichment, consuming your identities.

## Acceptance and Handoff

Verify pagination/counts, attachment signatures, extracted spans, identifier joins and
actor ambiguity on real sources. Time cached and uncached unfamiliar-law runs and retain
hardware, stage sizes, failures and latency. A context-only result is useful but does
not prove the influence path works. Record all limits in implementation status.

Integrate small PRs in dependency order and run relevant gates. Supply branches/PRs,
beads, schema version, fixture paths, real commands/results and blockers at each handoff.
Do not close consumer delivery beads merely because fixture tests pass. Open licence and
public repository release remain the owner's D6 decision; prepare reproducible outputs
and history/source review before that decision.
