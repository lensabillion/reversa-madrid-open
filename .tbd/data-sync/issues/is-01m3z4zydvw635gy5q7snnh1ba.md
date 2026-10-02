---
type: is
id: is-01m3z4zydvw635gy5q7snnh1ba
title: Show original law, amendment and lobby wording together
kind: feature
status: closed
priority: 2
version: 5
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T20:30:49.274Z
updated_at: 2026-10-02T21:15:04.568Z
started_at: 2026-10-02T20:31:11.413Z
closed_at: 2026-10-02T21:15:04.567Z
close_reason: "PR #13 merged 2026-10-02T21:09:01Z as 5f926a2; all nine PR and main CI checks passed. Three-column role captions and evidence behavior verified in browser and 38 frontend tests; README and implementation-status document the result."
resolution: null
duplicate_of: null
---
Replace text-version switching with original law, proposed amendment and lobby submission columns in historical evidence and supplied comparison results. Preserve source provenance and accurate insertion/deletion evidence, explicit unavailable originals, responsive stacking, regression checks and Markdown documentation. Deliver a separate first-principles PR.

## Notes

PR #13 ready for review: https://github.com/lensabillion/reversa-madrid-open/pull/13. All nine CI checks passed at commit a53ce31; gh pr checks --watch exited 0. Full make check: 106 backend tests with 100% branch coverage, 38 frontend tests, production build and clean audits. Three-column historical and supplied-text comparisons preserve original/proposed offsets, missing-data states and deletion evidence. Desktop equal-width and 390-pixel stacking browser checks passed; live deletion-only evidence verified. Independent review found no remaining issue. Documentation: frontend/README.md and docs/implementation-status.md. Remains open until merge.
