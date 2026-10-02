---
type: is
id: is-01m3ymycfd7dcbj83gb14j7t30
title: "Follow up the next@16.3.6 cool-off exception: confirm not yanked after 2026-10-06"
kind: chore
status: open
priority: 2
version: 2
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T15:50:20.909Z
updated_at: 2026-10-02T21:40:48.240Z
---
next 16.3.6 (published 2026-09-22) is pinned inside the 14-day window because 16.3.5 is vulnerable to GHSA-vcvr-r3jv-pc5j (critical RCE in next/og). After 2026-10-06 confirm 16.3.6 is not deprecated or yanked and remove the exception note.

## Notes

2026-10-02 23:40 CEST: the project owner (Lensa) confirmed in chat that they knowingly approved both TypeScript 7 and this next@16.3.6 cool-off exception (PRs #5 and #8). SUPPLY-CHAIN-SECURITY.md still says 'Pending project owner approval in this PR' in the Approved by column; correct that record in a separate docs PR.
