---
type: is
id: is-01m4b5ahvx2p1fytwd84eewv47
title: Preserve exact carrier intervals when matching lineage origins
kind: bug
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
created_at: 2026-10-07T12:27:30.044Z
updated_at: 2026-10-07T12:27:30.044Z
---
Parts 5-6. Reproduced disjoint 12-word alpha and beta amendments adjacent in final act merged into one phrase; alpha-only consultation incorrectly gets both amendment IDs. lineage.py:268-275,356-383; origin.py:225-240. Preserve per-carrier and origin interval evidence; intersect for edge creation and dates. Test disjoint adjacency, partial overlaps and unchanged deduplicated global coverage.
