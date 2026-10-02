---
type: is
id: is-01m3yrktj9x13xv22f83ntzbjv
title: "README: link the explainer page directly instead of its folder"
kind: task
status: closed
priority: 2
version: 4
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T16:54:29.192Z
updated_at: 2026-10-02T17:03:47.673Z
started_at: 2026-10-02T16:54:29.549Z
closed_at: 2026-10-02T17:03:47.673Z
close_reason: "On main: #3 (backend), #5 (frontend) and #6 (README) landed via #7 and #8, merged 2026-10-02 16:59 UTC (main 1f7202e). CI on main 1f7202e: Docs and scripts, Backend and Frontend workflows all succeeded."
resolution: null
duplicate_of: null
---
The README links docs/explainer/, which on GitHub opens a file list, and the HTML file then shows as raw code. Link the published page and name the source file.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/6 (base chore/project-rules).
