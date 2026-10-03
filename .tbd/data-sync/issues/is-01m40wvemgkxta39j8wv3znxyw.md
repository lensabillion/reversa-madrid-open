---
type: is
id: is-01m40wvemgkxta39j8wv3znxyw
title: Keep oversized submission passages from crashing the real Atlas run
kind: bug
status: in_progress
priority: 0
version: 5
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
hold: null
hold_until: null
created_at: 2026-10-03T12:47:02.287Z
updated_at: 2026-10-03T13:17:00.201Z
started_at: 2026-10-03T12:47:47.418Z
---
Real AIAct fullattachments run onmain2fbb229 failed after459.815seconds: assessment._best_reading constructs TextChange from an extracted tableofcontents-like ask >800tokens; pipeline.assess_candidates aborts entireview. PR47 bounds longamendments but notasks. Collection succeeded with29061passages/5660amendments/1088articles; no refreshedatlas.json written and oldemptyview remains. Implement explicit bounded handling preserving sourced offsets and reporting skipped/unsupported asks; regression must use >800token actualshape. No silenttruncation or inventedoldtext. Runcompletedbundle again andverifyGate3 outputs. Provenance data/raw/provenance/ai-act-e2e.*.json.

## Notes

PR #52 https://github.com/lensabillion/reversa-madrid-open/pull/52 now integrates main086d42a (PR48-51) atcecb869, final docs6e89093. Bounds fix preserves rules3/prose-unconfirmed defaults; original records retained. Full make check987backend/100%coverage(5627statements1462branches),94frontend, strict checks/build/audits pass;9CI green atcecb869. ACTUAL CLI exit0 in310.134s using cached public inputs: collection52.9s,retrieval212.381s/28229candidates,assessment29.392s,outcomes15.010s. Newrun20261003T130918Z:0published859unconfirmed82contradicted27288insufficient;graph1node0edges. Browser/API fresh run verified, noJSerrors/stale2links. Gate3 NOT passed:0<20 and no10sample; zero-span audit unavailable. OneHTTP400publication request remains partialcoverage;otherdownloads cached. No publicationoverride/paidAPI/manualedits. Full sources/timing/audit artifacts in ignored data/laws/2021-0106-COD, historicalrules2 snapshot separatelypreserved. Docs/implementation-status.md and PRbody carrydurableevidence. Keep openuntilmerge.
