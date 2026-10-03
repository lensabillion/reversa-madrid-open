---
type: is
id: is-01m40m06dz2jynxdvbrydqr03z
title: "Agent 3: build reusable Atlas evidence and explorer components"
kind: task
status: in_progress
priority: 0
version: 7
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfhe8qaj6srfqh1r6ada
hold: null
hold_until: null
created_at: 2026-10-03T10:12:20.543Z
updated_at: 2026-10-03T11:13:02.677Z
started_at: 2026-10-03T10:12:33.949Z
---
Prepare the part 8 evidence consumer while Agent 1 freezes GraphSnapshot. Scope: display-only source evidence, published/audit separation, loaded-record filters and component tests. No shared API schema, route, inference, graph projection or real-data completion. The separate UI integration child of rev-qn6b remains Agent 1 responsibility.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/24 now at da22878, incorporates PR25 shared contracts, PR27 retrieval and PR26 collection foundations. Graph-first workspace explains who asked / what matched / what survived; actual supplied graph nodes/edges open quotations and exact source comparison; missing/unpublished graph link IDs fail visibly. atlas-1 adapter supports joint actors and individual topics; multi-final/multi-source evidence representation remains limited and fails explicitly. Local make check-frontend:83 tests/11 files, Biome/types/build/audit clean. Browser verified graph -> selected quotations -> matching four-column source evidence. Synthetic LOCAL UNCOMMITTED /atlas-preview remains running port3013, excluded from PR. Agent1 names UI child rev-ifao in merged handoff, but tbd sync --pull then show reports issue not found; continue tracking here until that child syncs. Real collect orchestration/API and verification/outcomes still pending; PR26 documents unresolved amendment SourceDocument join. Agent3 full completion also needs report/enrichment/analysis hydration. Do not close before merge.
