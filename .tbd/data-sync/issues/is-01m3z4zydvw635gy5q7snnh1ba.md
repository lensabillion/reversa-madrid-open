---
type: is
id: is-01m3z4zydvw635gy5q7snnh1ba
title: Show original law, amendment and lobby wording together
kind: feature
status: in_progress
priority: 2
version: 3
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T20:30:49.274Z
updated_at: 2026-10-02T20:40:52.819Z
started_at: 2026-10-02T20:31:11.413Z
---
Replace text-version switching with original law, proposed amendment and lobby submission columns in historical evidence and supplied comparison results. Preserve source provenance and accurate insertion/deletion evidence, explicit unavailable originals, responsive stacking, regression checks and Markdown documentation. Deliver a separate first-principles PR.

## Notes

PR #13: https://github.com/lensabillion/reversa-madrid-open/pull/13. Three-column historical and supplied-text comparison implemented with shared evidence component; accurate original/proposed offset routing, missing-original states and deletion disclosure. Full make check passed: 106 backend tests, 100% branch coverage, 38 frontend tests, production build and clean audits. Independent review found no remaining issue. Browser confirmed equal desktop columns, 390-pixel stacking without overflow and live deletion evidence. Behavior and evaluation retained in frontend/README.md; handoff updated in docs/implementation-status.md. CI pending; remains open until merge.
