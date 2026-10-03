---
type: is
id: is-01m40nw41zbvnpsq0zexzfhx42
title: "Part 8 · Any-law command: CLI and thin API over parts 1-6 (Agent 1)"
kind: feature
status: closed
priority: 0
version: 3
delegate: claude-code@vm
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
hold: null
hold_until: null
created_at: 2026-10-03T10:45:04.190Z
updated_at: 2026-10-03T12:13:30.118Z
started_at: 2026-10-03T12:13:25.966Z
closed_at: 2026-10-03T12:13:30.118Z
close_reason: "Done in PR #45 (https://github.com/lensabillion/reversa-madrid-open/pull/45, merged 2026-10-03 at 127d3f5): influence collect and influence atlas on the CLI (make collect / make atlas), GET /api/v1/atlas and /api/v1/atlas/{slug} as thin read-only routers over services/pipeline.py, AtlasView schema atlas-view-1, RunManifest from collect. make check-backend: 673 passed, 100% branch coverage; all 9 CI checks green. Not done here and tracked on rev-qn6b: real-data timing on the demo laptop, common-name lookup (alias table)."
resolution: null
duplicate_of: null
---
CLI/API child of rev-qn6b, owned by Agent 1: influence collect <procedure> and influence atlas <query> on the existing CLI, thin atlas routers, run manifests. Files: backend/src/influence/cli.py, api.py, routers/atlas*.py, schemas/atlas.py.
