---
type: is
id: is-01m3yq5jh751jzk4q5n7m8d59q
title: Guard against a basedpyright baseline file silently downgrading type errors
kind: chore
status: open
priority: 3
version: 1
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T16:29:13.638Z
updated_at: 2026-10-02T16:29:13.638Z
---
A .basedpyright/baseline.json would turn baselined errors into hints while the type gate stays green. Add a gate probe or check that fails if a baseline file exists.
