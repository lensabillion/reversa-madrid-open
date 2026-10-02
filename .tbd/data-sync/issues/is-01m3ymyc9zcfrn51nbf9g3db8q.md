---
type: is
id: is-01m3ymyc9zcfrn51nbf9g3db8q
title: "PR: frontend foundation (Next.js 16.3.6, strict TypeScript, Biome, Vitest, CI)"
kind: task
status: in_progress
priority: 1
version: 4
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies:
  - type: blocks
    target: is-01m3ymycfd7dcbj83gb14j7t30
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T15:50:20.734Z
updated_at: 2026-10-02T16:41:15.206Z
started_at: 2026-10-02T15:57:46.508Z
---
frontend/ Next.js App Router project written by hand (no generator), tsconfig floor, Biome floor with probes, Vitest component test, npm with ignore-scripts and 14-day min-release-age, GitHub Actions workflow pinned by SHA.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/5 (base feat/backend-foundation). Commits b990d65 (agent build) + 277564f (review: target names, Next agent block, docs). make check exit 0 from clean (16 s); visual check at 1280/375/320, light and dark.
