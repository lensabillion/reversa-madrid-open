---
type: is
id: is-01m3z9031tbyyn62ks5s0m2wze
title: Add a project skill that makes agents fit every feature into the agreed seven-part architecture
kind: task
status: in_progress
priority: 1
version: 3
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T21:40:48.313Z
updated_at: 2026-10-02T21:48:08.887Z
started_at: 2026-10-02T21:40:51.540Z
---
The user asked for a skill that tells any agent working on a feature to follow the architecture in docs/explainer/influence-graph-primer.md section 11. PRs #10-#14 drifted from it (demo before the CSV path, graph from historical labels, a second matcher), and the attic prototype predates the architecture, so it must not be built on. Deliver one SKILL.md visible to Claude Code (.claude/skills) and Codex (.agents/skills), plus a pointer in AGENTS.md, as one first-principles PR.

## Notes

PR #16 https://github.com/lensabillion/reversa-madrid-open/pull/16 opened 2026-10-02: skill at .agents/skills/influence-architecture/SKILL.md, symlink in .claude/skills, AGENTS.md workflow step 3, D3 decided. make check exit 0 (110 backend, 38 frontend tests, 100% coverage). Claude Code discovery verified in a live session; Codex discovery per its docs only. Close when #16 merges.
