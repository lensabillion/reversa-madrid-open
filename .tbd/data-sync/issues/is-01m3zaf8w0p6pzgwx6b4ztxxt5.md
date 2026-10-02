---
type: is
id: is-01m3zaf8w0p6pzgwx6b4ztxxt5
title: Remove unused API routes /api/v1/score and /api/v1/organizations
kind: chore
status: open
priority: 2
version: 1
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T22:06:34.367Z
updated_at: 2026-10-02T22:06:34.367Z
---
Owner-approved 2026-10-03. /score duplicates /compare (one implementation per job; the frontend and the step 1 command use compare_texts). /organizations is unused and counts organizations from 2013 labels (violates the part 4 -> part 5 arrow). Start after PR #17 merges, because both edit the demo router, service, schemas, tests and rehearse_demo.py.
