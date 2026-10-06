---
type: is
id: is-01m48s1nq2ytddfcr2m3ebmyzg
title: Remove the source-map-js 1.2.2 exception row from SUPPLY-CHAIN-SECURITY.md once it clears the cool-off
kind: chore
status: open
priority: 3
version: 1
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
deferred_until: 2026-10-14T00:00:00.000Z
created_at: 2026-10-06T14:14:27.298Z
updated_at: 2026-10-06T14:14:27.298Z
---
Outside the pipeline (supply chain). The exception taken in PR #89 (GHSA-68fv-2mgg-jv7q) clears the 14-day window on 2026-10-14; the policy says an expired exception row is removed. Delete the row and note 2 from the Exceptions section; nothing else changes (the lockfile already holds 1.2.2).
