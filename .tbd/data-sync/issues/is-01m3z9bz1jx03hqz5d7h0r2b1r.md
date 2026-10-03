---
type: is
id: is-01m3z9bz1jx03hqz5d7h0r2b1r
title: Network tab on the frontend does not make sense to the project owner
kind: bug
status: closed
priority: 1
version: 5
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T21:47:17.425Z
updated_at: 2026-10-03T08:48:02.565Z
started_at: 2026-10-02T21:59:35.110Z
closed_at: 2026-10-03T08:48:02.565Z
close_reason: "PR #17 merged 2026-10-03 08:32Z as 000d779: Network tab, its component, types, test and GET /api/v1/amendments/{id}/graph removed. All CI checks passed. A real graph from our own links is now planned under the Influence Atlas brief."
resolution: null
duplicate_of: null
---
Owner feedback, 2026-10-02 23:55: 'The network tab doesn't make sense' (frontend/components/influence-network.tsx). Audit context: the graph (architecture part 5) is built in backend services/demo.py from LobbyPlag's 2013 historically verified links, not from our scored links, and shows no win rates; the agreed demo (part 7) is tracer, map and scoreboard. Investigate what the tab shows, explain it to the owner, and fix it as part of plan step 6 (graph and scoreboard from our own scores), unless the owner reprioritizes.

## Notes

PR #17 https://github.com/lensabillion/reversa-madrid-open/pull/17 (fix/remove-network-tab): removes the Network tab, its component/types/test and GET /api/v1/amendments/{id}/graph. make check exit 0 (108 backend, 37 frontend tests, 100% coverage of 451 statements/98 branches); new regression assertions fail on old code; browser check at desktop and 390 px. Real graph from part 4's links is plan step 6. Close when #17 merges.
