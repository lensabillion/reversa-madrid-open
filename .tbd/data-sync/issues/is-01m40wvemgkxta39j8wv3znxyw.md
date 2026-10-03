---
type: is
id: is-01m40wvemgkxta39j8wv3znxyw
title: Keep oversized submission passages from crashing the real Atlas run
kind: bug
status: in_progress
priority: 0
version: 4
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
hold: null
hold_until: null
created_at: 2026-10-03T12:47:02.287Z
updated_at: 2026-10-03T13:02:52.562Z
started_at: 2026-10-03T12:47:47.418Z
---
Real AIAct fullattachments run onmain2fbb229 failed after459.815seconds: assessment._best_reading constructs TextChange from an extracted tableofcontents-like ask >800tokens; pipeline.assess_candidates aborts entireview. PR47 bounds longamendments but notasks. Collection succeeded with29061passages/5660amendments/1088articles; no refreshedatlas.json written and oldemptyview remains. Implement explicit bounded handling preserving sourced offsets and reporting skipped/unsupported asks; regression must use >800token actualshape. No silenttruncation or inventedoldtext. Runcompletedbundle again andverifyGate3 outputs. Provenance data/raw/provenance/ai-act-e2e.*.json.

## Notes

PR #52 https://github.com/lensabillion/reversa-madrid-open/pull/52 contains the bounded-ask fix (104e462) and measured status (7d67fb4). Parts 3/4 validate all parsed readings with existing TextChange bounds before retrieval; retain original records and explicit excluded IDs/count/reasons. Direct invalid assessment is insufficient_evidence. Full make check passed: 751 backend tests, 100% coverage (4780 statements/1182 branches), 94 frontend tests, production build, strict checks and clean audits. Cached real AI Act build completed in249.318s from run20261003T123800Z: retrieval221.605s/28229candidates, assessment15.945s, trace11.235s; 2published,646unconfirmed,11357contradicted,7nodes/6edges. Gate3 fails2<20; no10sample possible. Both published links share an AI HLEG definition, not established submission-specific origins. No full CLI success claimed. Artifacts under data/laws/2021-0106-COD include timing, audit-seed0, agent-review and source-provenance; raw outputs unchanged. All27link/12outcome/29graph spans exact; no final-act evidence spans for published links. Keep open until merge.
