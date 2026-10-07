---
name: influence-architecture
description: >-
  Fit work into influence's maintained lineage website: public collection and actor
  resolution, adopted/tabled wording, optional reworded origins, lineage records,
  read-only API and explorer. Use before planning, design, code or PRs in this repository.
---

# Fit Work Into the Maintained Lineage Architecture

The owner chose a lineage-only product on 7 October 2026 (`rev-w1ao`), after inspecting
and rejecting the temporary Saved analysis page. This decision supersedes the broader
challenge implementation scope. The project name is **influence**. Documents describing
the original eight-part challenge design remain historical research and decision records.
The [backend guide](../../../backend/README.md) and
[implementation status](../../../docs/implementation-status.md) define current behavior.

## Current Path

```text
setup → collect → lineage → lineage.json → GET /api/v1/lineage → /lineage
```

| Responsibility | Retained behavior |
| --- | --- |
| Public collection | Resolve a law; obtain proposal/final text, amendments, consultation documents and actors; preserve URLs, retrieval dates, hashes, coverage and run manifests |
| Actor resolution | Register/MEP identities and normalized names in collected records |
| Wording lineage | Identify new final wording and carrying amendments; find earlier consultation wording and tabled-only matches with explicit eligibility |
| Optional semantic origins | Existing BM25 shortlist and Jev judgment, enabled only by CLI `--jev`, with existing request bounds, cache and spend cap |
| Persisted view | `lineage.json`, new schema `lineage-2` with exact lexical carrier supports; read legacy `lineage-1` without fabricating evidence |
| Read-only API | Health and lineage list/detail; caching, validation and explicit missing/error states |
| Website | Existing lineage summary, holders, graph, evidence, sample and method; backend supplies records, frontend derives its existing organisation aggregates and layout |
| Quality tooling | Independent lineage review with separate human labels; locked installs, Ruff/Biome, strict types, behavioral tests, gate probes, dependency audits and container checks |

The `atlas.json` producer, ask-first graph/outcome/forecast/report/audit branch, standalone
channels/directions/coordinated/batch commands, extraction probe CLI and practice/model
experiment runners are retired. Keep `influence.practice.lineage_review` and its tests:
it reviews current lineage claims and is quality tooling even though HTTP never calls it.
Its phrase sample differs from the graph population, and its precision uses resolved
agreements; do not treat it as a completed independent accuracy audit.
Do not restore a retired feature merely because a dated
plan describes it. Existing documents, evaluation JSON and ignored user data are preserved.
The shared collection schema's `atlas-1` identifier is a persisted contract, not an active
Atlas pipeline; keep compatible records rather than renaming stored fields gratuitously.

## Before Designing or Editing

1. Read implementation status and the relevant current backend contract; claim the bead
   through tbd. Name the retained responsibility the change supports.
2. Extend the existing implementation in that responsibility. Do not add a second loader,
   matcher or graph builder. If changing product scope, obtain an owner decision; an
   explicit instruction in the current session already supplies that authorization.
3. Follow the dependency direction: UI → read-only API → saved lineage view; CLI lineage
   → collection and lineage services → repositories/extraction utilities. HTTP reads do
   not run collection or paid models.
4. Preserve exact source identity, spans, unknown states, timestamps and coverage. Shared
   wording or a model judgment is not proof of influence. The review's existing lineage
   publication/attribution limitations remain open; removing Atlas does not fix them.
5. Keep raw output separate from human labels and never edit links/counts/rankings by hand.
   Scoring changes need appropriate evaluation evidence, not just green unit tests.
6. Test the boundary being changed, including malformed/missing data and relevant invariants.
   Preserve gate probes and the coverage threshold; do not keep retired code solely for
   tests, but retain meaningful tests of shared helpers moved into lineage.
7. Record behavior, verification and decisions in the repository. Fill the PR template
   from first principles, distinguishing measured facts from unperformed acceptance work.

## Shared Helpers and Historical Code

When removing a module, trace its live imports first. Collection bundle loading, token
bounds, changed-word extraction, BM25 candidate ordering, source spans and Jev request
bytes are used by lineage even if their former module name included Atlas. Move the live
logic to the existing collection/lineage responsibility and verify behavioral equivalence.

`attic/` predates the architecture. Do not import, copy or treat it as an implementation
source. Historical documents and measurements are evidence records; an old command in
them is not a current executable contract. The current guide identifies supported commands.
