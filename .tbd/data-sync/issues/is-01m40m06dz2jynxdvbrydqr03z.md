---
type: is
id: is-01m40m06dz2jynxdvbrydqr03z
title: "Agent 3: build reusable Atlas evidence and explorer components"
kind: task
status: in_progress
priority: 0
version: 5
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfhe8qaj6srfqh1r6ada
hold: null
hold_until: null
created_at: 2026-10-03T10:12:20.543Z
updated_at: 2026-10-03T10:26:51.768Z
started_at: 2026-10-03T10:12:33.949Z
---
Prepare the part 8 evidence consumer while Agent 1 freezes GraphSnapshot. Scope: display-only source evidence, published/audit separation, loaded-record filters and component tests. No shared API schema, route, inference, graph projection or real-data completion. The separate UI integration child of rev-qn6b remains Agent 1 responsibility.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/24 final commit 933385a: all 9 CI checks passed; 56 frontend tests, 192 backend tests with 100% branch coverage, production build, types/lint/catalogs and both audits green. Presentation only: evidence/explorer plus supplied analysis/report views. Astra review fixed empty final text, stale invisible filters and denominator mismatch. Full wins use supplied assessedAsks, unknown separate; all-unknown rate unavailable. Explorer/evidence desktop and 390px mobile preview inspected; analysis component tests only. Shared GraphSnapshot, live adapter, graph construction, ranking calculations, report generation and real-data rehearsal remain pending under rev-i006 and dependent beads. Keep open until merge.
