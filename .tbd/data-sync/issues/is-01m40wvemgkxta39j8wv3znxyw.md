---
type: is
id: is-01m40wvemgkxta39j8wv3znxyw
title: Keep oversized submission passages from crashing the real Atlas run
kind: bug
status: in_progress
priority: 0
version: 3
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
hold: null
hold_until: null
created_at: 2026-10-03T12:47:02.287Z
updated_at: 2026-10-03T12:58:26.963Z
started_at: 2026-10-03T12:47:47.418Z
---
Real AIAct fullattachments run onmain2fbb229 failed after459.815seconds: assessment._best_reading constructs TextChange from an extracted tableofcontents-like ask >800tokens; pipeline.assess_candidates aborts entireview. PR47 bounds longamendments but notasks. Collection succeeded with29061passages/5660amendments/1088articles; no refreshedatlas.json written and oldemptyview remains. Implement explicit bounded handling preserving sourced offsets and reporting skipped/unsupported asks; regression must use >800token actualshape. No silenttruncation or inventedoldtext. Runcompletedbundle again andverifyGate3 outputs. Provenance data/raw/provenance/ai-act-e2e.*.json.

## Notes

Atlas parts 3 and 4. Fix validates every parsed ask reading with the existing TextChange bounds before indexing, so unsupported asks cannot crowd the shortlist. View limitations retain rejected ask IDs, reasons and count; original collected records and offsets remain unchanged. Direct assessment returns insufficient_evidence for unsupported asks. Regression includes <120 whitespace words but >800 punctuation tokens, quoted replacement/deletion/mixed instructions, blank input, valid bounded reading in long context and a normal neighbor that still publishes. make check passed; exact output /tmp/atlas-oversized-ask-make-check.log. Source hashes: assessment.py 2db3efedffe56042e7e525ce51e75d71c444a4059882d4f5eb6cc9e264c64f5c; pipeline.py fc9cdc063274dadca9f8fb1629547e742058752baa73ff54d6d97086d441bb5b. Added deterministic punctuation-only outcome regression because the full gate previously depended on Hypothesis reaching that guard. Cached real-law rerun is in progress with another agent; no precision/audit improvement claimed.
