---
type: is
id: is-01m3ymyc4fg91184t8wq7gajt0
title: "PR: backend foundation (Python 3.14, uv, FastAPI, ruff, basedpyright, pytest, CI)"
kind: task
status: in_progress
priority: 1
version: 5
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
updated_at: 2026-10-02T16:29:13.638Z
started_at: 2026-10-02T15:57:46.344Z
---
backend/ uv project with src layout, typed settings, FastAPI app factory with a health route, strict lint/format/type/test gates with config-contract probes, one make check entry point, GitHub Actions workflow pinned by SHA.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/3 (base chore/project-rules). Commits 239bb35 (agent build, reviewed) + 26c8a50 (docs, fix-target order). make check exit 0 locally.
