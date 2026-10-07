---
type: is
id: is-01m4bbxzcbhy63je8vtghf4ewk
title: Replace README process illustration with a technical architecture diagram
kind: task
status: in_progress
priority: 2
version: 5
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-07T14:22:57.931Z
updated_at: 2026-10-07T15:16:11.606Z
started_at: 2026-10-07T14:23:27.087Z
---
Owner requested a professional architecture diagram in the main README. Describe the maintained lineage system with correct boundaries, persisted data, labeled request/data flows, optional Jev origins and separate review tooling. Use native SVG, review architecture independently, render and inspect at README width. Preserve current runtime and avoid claiming pending accuracy fixes.

## Notes

PR #105 architecture remains published at 4ed8327 with all 10 checks green. Owner requested removal of the README brief-history paragraph; local commit 4b96e7e removes exactly that paragraph and passes diff check. GitHub rejected push on 7 Oct 2026 at 15:14 UTC with Internal Server Error; removal is not yet published. Source worktree architecture-readme retained.
