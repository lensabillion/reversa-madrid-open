---
type: is
id: is-01m40m06dz2jynxdvbrydqr03z
title: "Agent 3: build reusable Atlas evidence and explorer components"
kind: task
status: in_progress
priority: 0
version: 4
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfhe8qaj6srfqh1r6ada
hold: null
hold_until: null
created_at: 2026-10-03T10:12:20.543Z
updated_at: 2026-10-03T10:24:41.143Z
started_at: 2026-10-03T10:12:33.949Z
---
Prepare the part 8 evidence consumer while Agent 1 freezes GraphSnapshot. Scope: display-only source evidence, published/audit separation, loaded-record filters and component tests. No shared API schema, route, inference, graph projection or real-data completion. The separate UI integration child of rev-qn6b remains Agent 1 responsibility.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/24 at 5e34557: all 9 CI checks green after Astra review. Added regressions and fixes for known-empty final text and unavailable selected topic/year after snapshot refresh; 11 focused evidence/explorer tests pass. Quote mismatches carry explicit evidence verification warning. Shared snapshot adapter and real-data integration remain absent. Broader independent analysis-view slice is rev-1jc4 and will be reviewed in the same presentation PR; graph calculations remain rev-i006/rev-5yy6.
