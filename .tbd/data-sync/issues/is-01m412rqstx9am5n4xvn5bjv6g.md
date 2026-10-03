---
type: is
id: is-01m412rqstx9am5n4xvn5bjv6g
title: Replace Atlas raw diagnostic wall with readable coverage summary and expandable details
kind: bug
status: in_progress
priority: 1
version: 4
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-03T14:30:24.825Z
updated_at: 2026-10-03T14:46:02.100Z
started_at: 2026-10-03T14:31:19.539Z
---
Part 8 frontend UX: screenshot shows joined raw limitations and record IDs filling the page. Preserve all diagnostics and coverage truth, summarize the method/partial analysis in plain language, and put raw record IDs/errors behind native expandable details. No scoring or data changes. Verify against the real AI Act view and frontend tests.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/69 ready for review. Final head fb2934e16a73b25db9a16fbe3adfe03338789021 integrates latest main source-coverage UI; all 9 GitHub checks completed successfully. Full local make check exited 0: 1224 backend tests, 100% branch coverage, 117 frontend tests, production build, lint/types/gate probes, both audits clean. Browser verified compact collapsed notice and expansion/collapse preserving diagnostics; latest real-data view also shows source badges and explains 941 unpublished candidates. Preview left open at http://localhost:3015/atlas?law=2021-0106-COD. Bead remains in progress until merge.
