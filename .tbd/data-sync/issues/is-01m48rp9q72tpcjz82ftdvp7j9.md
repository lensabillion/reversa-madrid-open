---
type: is
id: is-01m48rp9q72tpcjz82ftdvp7j9
title: "Take source-map-js 1.2.2 inside the 14-day cool-off: GHSA-68fv-2mgg-jv7q fails the frontend audit gate"
kind: chore
status: closed
priority: 1
version: 4
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-06T14:08:14.566Z
updated_at: 2026-10-06T14:14:27.221Z
started_at: 2026-10-06T14:08:14.854Z
closed_at: 2026-10-06T14:14:27.221Z
close_reason: "PR #89 merged by the owner on 2026-10-06 (approval of the cool-off exception by merging, as the policy's precedent). Lockfile moved source-map-js 1.2.1 -> 1.2.2; all nine CI checks green on the PR, including the frontend audit."
resolution: null
duplicate_of: null
---
Outside the pipeline (supply chain). Since 2026-10-06 'npm audit --audit-level=moderate' fails on main with GHSA-68fv-2mgg-jv7q (CVE-2026-93749, high): source-map-js 1.2.1, a transitive build-time dependency of postcss, @tailwindcss/node and jsdom's css-tree. The first fixed version 1.2.2 was published 2026-09-30, inside the cool-off, so npm audit fix under frontend/.npmrc finds nothing and every PR's audit check is red. Needs a recorded exception approved by the owner (SUPPLY-CHAIN-SECURITY.md rule 1); clears the window on 2026-10-14.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/89 opened 2026-10-06: lockfile moves source-map-js 1.2.1 -> 1.2.2 (package.json unchanged), exception row + note 2 in SUPPLY-CHAIN-SECURITY.md. Verified: GitHub compare v1.2.1...v1.2.2 (4 commits, lib/ and test/ only), integrity equals the registry's, npm audit clean, make check-frontend green. Approval = the owner merging. Remove the row on/after 2026-10-14.
