---
type: is
id: is-01m3z9bz1jx03hqz5d7h0r2b1r
title: Network tab on the frontend does not make sense to the project owner
kind: bug
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T21:47:17.425Z
updated_at: 2026-10-02T21:47:17.425Z
---
Owner feedback, 2026-10-02 23:55: 'The network tab doesn't make sense' (frontend/components/influence-network.tsx). Audit context: the graph (architecture part 5) is built in backend services/demo.py from LobbyPlag's 2013 historically verified links, not from our scored links, and shows no win rates; the agreed demo (part 7) is tracer, map and scoreboard. Investigate what the tab shows, explain it to the owner, and fix it as part of plan step 6 (graph and scoreboard from our own scores), unless the owner reprioritizes.
