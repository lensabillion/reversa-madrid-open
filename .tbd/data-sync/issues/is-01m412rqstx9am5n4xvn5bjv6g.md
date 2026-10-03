---
type: is
id: is-01m412rqstx9am5n4xvn5bjv6g
title: Replace Atlas raw diagnostic wall with readable coverage summary and expandable details
kind: bug
status: in_progress
priority: 1
version: 3
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-03T14:30:24.825Z
updated_at: 2026-10-03T14:43:56.545Z
started_at: 2026-10-03T14:31:19.539Z
---
Part 8 frontend UX: screenshot shows joined raw limitations and record IDs filling the page. Preserve all diagnostics and coverage truth, summarize the method/partial analysis in plain language, and put raw record IDs/errors behind native expandable details. No scoring or data changes. Verify against the real AI Act view and frontend tests.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/69. Compact summary and native collapsed details preserve all method/limitation text and record IDs. Browser checked expansion/collapse against the real AI Act API; preview http://localhost:3015/atlas?law=2021-0106-COD. Initial make check passed (1150 backend, 96 frontend tests, 100% backend coverage, build and audits). Integrated newer origin/main after CI exposed its new coverage fixture using the old notice type; adapted that fixture, pushed fb2934e, rerunning complete gate and CI.
