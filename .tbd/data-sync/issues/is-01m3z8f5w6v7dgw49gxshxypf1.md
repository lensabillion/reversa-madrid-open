---
type: is
id: is-01m3z8f5w6v7dgw49gxshxypf1
title: Keep project state and decisions in the repository, not in sessions
kind: task
status: closed
priority: 1
version: 4
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T21:31:34.149Z
updated_at: 2026-10-02T21:55:47.133Z
started_at: 2026-10-02T21:31:34.481Z
closed_at: 2026-10-02T21:55:47.133Z
close_reason: "PR #15 merged into main 2026-10-02 21:34 UTC; all 9 CI checks passed. AGENTS.md now requires sessions to start from docs/implementation-status.md and tbd and record state before ending; Decisions section added."
resolution: null
duplicate_of: null
---
Add an AGENTS.md rule that session memory is not a source of truth, plus docs/project/state.md (what is built per architecture part, priorities, risks) and docs/project/decisions.md (decision log with status and reasons). Every session starts by reading them and updates them before it ends.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/15
