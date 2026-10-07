---
type: is
id: is-01m4b5ahvx2p1fytwd84eewv47
title: Preserve exact carrier intervals when matching lineage origins
kind: bug
status: in_progress
priority: 1
version: 5
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
hold: null
hold_until: null
created_at: 2026-10-07T12:27:30.044Z
updated_at: 2026-10-07T15:51:10.984Z
started_at: 2026-10-07T14:04:27.017Z
---
Parts 5-6. Reproduced disjoint 12-word alpha and beta amendments adjacent in final act merged into one phrase; alpha-only consultation incorrectly gets both amendment IDs. lineage.py:268-275,356-383; origin.py:225-240. Preserve per-carrier and origin interval evidence; intersect for edge creation and dates. Test disjoint adjacency, partial overlaps and unchanged deduplicated global coverage.

## Notes

PR #106 conflict resolved and pushed as 8b00100, merging main f116800. Preserved the professional diagram from merged #105, both requested README paragraph removals, lineage-2 compatibility wording, and all repair notes. Only three documentation files changed in the merge; independent Astra review approved the exact staged diff. SVG XML/accessibility, conflict-marker and whitespace checks passed; make check-docs check-scripts passed (6 catalogs, Ruff). GitHub now reports MERGEABLE; final CI remains in progress. The branch also includes #107 sampling, merged by the owner. Website is running on localhost:3052 with API8052 and four temporary rehearsal snapshots.
