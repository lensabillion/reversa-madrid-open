---
type: is
id: is-01m4b5ahvx2p1fytwd84eewv47
title: Preserve exact carrier intervals when matching lineage origins
kind: bug
status: in_progress
priority: 1
version: 4
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
hold: null
hold_until: null
created_at: 2026-10-07T12:27:30.044Z
updated_at: 2026-10-07T15:28:05.413Z
started_at: 2026-10-07T14:04:27.017Z
---
Parts 5-6. Reproduced disjoint 12-word alpha and beta amendments adjacent in final act merged into one phrase; alpha-only consultation incorrectly gets both amendment IDs. lineage.py:268-275,356-383; origin.py:225-240. Preserve per-carrier and origin interval evidence; intersect for edge creation and dates. Test disjoint adjacency, partial overlaps and unchanged deduplicated global coverage.

## Notes

PR106 targetsmain,head4db5d62 all10CIchecksSUCCESS,CLEAN/MERGEABLE. IncludesR7count/R1labelsfromclosedstackPR103/104whichhadnotreachedmain. Backend679tests100%,frontend83tests,400caseoracle,221supports663rawslicesfrom4laws,328sourcefilesunchanged. No source snapshots overwritten.
