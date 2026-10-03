---
type: is
id: is-01m40wvemgkxta39j8wv3znxyw
title: Keep oversized submission passages from crashing the real Atlas run
kind: bug
status: in_progress
priority: 0
version: 2
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
hold: null
hold_until: null
created_at: 2026-10-03T12:47:02.287Z
updated_at: 2026-10-03T12:47:47.419Z
started_at: 2026-10-03T12:47:47.418Z
---
Real AIAct fullattachments run onmain2fbb229 failed after459.815seconds: assessment._best_reading constructs TextChange from an extracted tableofcontents-like ask >800tokens; pipeline.assess_candidates aborts entireview. PR47 bounds longamendments but notasks. Collection succeeded with29061passages/5660amendments/1088articles; no refreshedatlas.json written and oldemptyview remains. Implement explicit bounded handling preserving sourced offsets and reporting skipped/unsupported asks; regression must use >800token actualshape. No silenttruncation or inventedoldtext. Runcompletedbundle again andverifyGate3 outputs. Provenance data/raw/provenance/ai-act-e2e.*.json.
