---
type: is
id: is-01m4b5ahvx2p1fytwd84eewv47
title: Preserve exact carrier intervals when matching lineage origins
kind: bug
status: in_progress
priority: 1
version: 6
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
hold: null
hold_until: null
created_at: 2026-10-07T12:27:30.044Z
updated_at: 2026-10-07T15:51:43.504Z
started_at: 2026-10-07T14:04:27.017Z
---
Parts 5-6. Reproduced disjoint 12-word alpha and beta amendments adjacent in final act merged into one phrase; alpha-only consultation incorrectly gets both amendment IDs. lineage.py:268-275,356-383; origin.py:225-240. Preserve per-carrier and origin interval evidence; intersect for edge creation and dates. Test disjoint adjacency, partial overlaps and unchanged deduplicated global coverage.

## Notes

PR #106 conflict repair 8b00100 verified complete: all 10 CI checks SUCCESS, GitHub CLEAN and MERGEABLE against main f116800. Independent Astra review approved the documentation-only resolution. Professional diagram, both README removals, lineage-2 contract and all R1/R2/R5/R7 notes are preserved. Runtime changes were not required for this merge. PR description now includes merged #107 sampling and final exact-head CI evidence. No PR merged by this agent.
