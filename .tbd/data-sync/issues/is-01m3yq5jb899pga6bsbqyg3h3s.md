---
type: is
id: is-01m3yq5jb899pga6bsbqyg3h3s
title: Upgrade Starlette to 1.7.0+ after 2026-10-07 and remove the anyio warning exception
kind: chore
status: open
priority: 3
version: 1
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T16:29:13.448Z
updated_at: 2026-10-02T16:29:13.448Z
---
backend/pyproject.toml ignores one anyio BlockingPortal deprecation from starlette.testclient (Starlette 1.6.0). Starlette 1.7.0 fixes it and clears the 14-day cool-off on 2026-10-07. Check FastAPI compatibility, re-lock, delete the filterwarnings exception.
