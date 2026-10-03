---
type: is
id: is-01m40m06dz2jynxdvbrydqr03z
title: "Agent 3: build reusable Atlas evidence and explorer components"
kind: task
status: in_progress
priority: 0
version: 3
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfhe8qaj6srfqh1r6ada
hold: null
hold_until: null
created_at: 2026-10-03T10:12:20.543Z
updated_at: 2026-10-03T10:17:55.303Z
started_at: 2026-10-03T10:12:33.949Z
---
Prepare the part 8 evidence consumer while Agent 1 freezes GraphSnapshot. Scope: display-only source evidence, published/audit separation, loaded-record filters and component tests. No shared API schema, route, inference, graph projection or real-data completion. The separate UI integration child of rev-qn6b remains Agent 1 responsibility.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/24 at 2d774c2: all 9 CI checks green. Local frontend 46 tests, backend 192 tests and 100% branch coverage, build/types/lint/catalogs/audits passed; desktop and 390px synthetic preview inspected. No live route or shared snapshot adapter. Awaiting merge; keep open. Additional Astra review running at user request.
