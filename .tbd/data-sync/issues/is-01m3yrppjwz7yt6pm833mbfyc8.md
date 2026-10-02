---
type: is
id: is-01m3yrppjwz7yt6pm833mbfyc8
title: Land the merged stack on main (research docs, backend, datasets, frontend)
kind: task
status: in_progress
priority: 1
version: 3
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T16:56:03.419Z
updated_at: 2026-10-02T16:56:46.879Z
started_at: 2026-10-02T16:56:03.723Z
---
PRs #2-#5 merged into intermediate branches after #1 had merged into main, so their content is not on main. Land chore/project-rules (docs, backend, datasets, README fix #6) and then feat/backend-foundation (frontend) into main.

## Notes

Landing PRs: #7 chore/project-rules -> main (docs #2, backend #3, datasets #4, README #6 if merged first); #8 feat/backend-foundation -> main (frontend #5). Merge #6, #7, then #8.
