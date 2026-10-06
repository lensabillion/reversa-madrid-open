---
type: is
id: is-01m48xymm3raqhb5c6jrxnjykv
title: "Take sharp 0.35.5 inside the 14-day cool-off: GHSA-wq5f-xc86-pv6w fails the frontend audit gate"
kind: chore
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-06T15:40:10.755Z
updated_at: 2026-10-06T15:40:10.755Z
---
Outside the pipeline (supply chain). Published 2026-10-06 13:43 UTC: GHSA-wq5f-xc86-pv6w (CVE-2026-96889, high, a librsvg vulnerability inside sharp's bundled libraries) in sharp < 0.35.5. sharp 0.35.4 is an optional dependency of next 16.3.6 in frontend/package-lock.json, so main's own audit gate fails and every PR's audit check is red. The first fixed version 0.35.5 was published 2026-09-27, inside the cool-off (clears 2026-10-11), so npm audit fix under frontend/.npmrc finds nothing; needs a recorded exception approved by the owner by merging, as PR #89 did for source-map-js.
