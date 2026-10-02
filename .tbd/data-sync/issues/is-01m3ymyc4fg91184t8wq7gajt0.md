---
type: is
id: is-01m3ymyc4fg91184t8wq7gajt0
title: "PR: backend foundation (Python 3.14, uv, FastAPI, ruff, basedpyright, pytest, CI)"
kind: task
status: closed
priority: 1
version: 6
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies:
  - type: blocks
    target: is-01m3yq5jb899pga6bsbqyg3h3s
  - type: blocks
    target: is-01m3yq5jh751jzk4q5n7m8d59q
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T15:50:20.559Z
updated_at: 2026-10-02T17:03:47.658Z
started_at: 2026-10-02T15:57:46.344Z
closed_at: 2026-10-02T17:03:47.658Z
close_reason: "On main: #3 (backend), #5 (frontend) and #6 (README) landed via #7 and #8, merged 2026-10-02 16:59 UTC (main 1f7202e). CI on main 1f7202e: Docs and scripts, Backend and Frontend workflows all succeeded."
resolution: null
duplicate_of: null
---
backend/ uv project with src layout, typed settings, FastAPI app factory with a health route, strict lint/format/type/test gates with config-contract probes, one make check entry point, GitHub Actions workflow pinned by SHA.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/3 (base chore/project-rules). Commits 239bb35 (agent build, reviewed) + 26c8a50 (docs, fix-target order). make check exit 0 locally.
