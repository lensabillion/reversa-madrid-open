---
type: is
id: is-01m40m06dz2jynxdvbrydqr03z
title: "Agent 3: build reusable Atlas evidence and explorer components"
kind: task
status: in_progress
priority: 0
version: 6
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfhe8qaj6srfqh1r6ada
hold: null
hold_until: null
created_at: 2026-10-03T10:12:20.543Z
updated_at: 2026-10-03T10:28:54.900Z
started_at: 2026-10-03T10:12:33.949Z
---
Prepare the part 8 evidence consumer while Agent 1 freezes GraphSnapshot. Scope: display-only source evidence, published/audit separation, loaded-record filters and component tests. No shared API schema, route, inference, graph projection or real-data completion. The separate UI integration child of rev-qn6b remains Agent 1 responsibility.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/24 at 933385a: all 9 CI checks passed, 56 frontend tests, 192 backend tests/full branch coverage, build/types/lint/catalogs/audits green. Display components only; shared GraphSnapshot, graph calculations, live adapter and real-data demo remain pending. On user request, added LOCAL UNCOMMITTED frontend/app/atlas-preview/page.tsx in atlas-agent-three worktree and started dev server on port3013; http://localhost:3013/atlas-preview shows actual components with prominently labelled synthetic examples, analysis at #analysis. Browser verified explorer and analysis layouts. Preview route is not in PR24; retain while user is reviewing, remove before any production commit. Keep task open until PR merge.
