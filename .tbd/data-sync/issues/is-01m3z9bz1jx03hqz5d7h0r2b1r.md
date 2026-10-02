---
type: is
id: is-01m3z9bz1jx03hqz5d7h0r2b1r
title: Network tab on the frontend does not make sense to the project owner
kind: bug
status: open
priority: 1
version: 2
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T21:47:17.425Z
updated_at: 2026-10-02T21:52:44.568Z
---
Owner feedback, 2026-10-02 23:55: 'The network tab doesn't make sense' (frontend/components/influence-network.tsx). Audit context: the graph (architecture part 5) is built in backend services/demo.py from LobbyPlag's 2013 historically verified links, not from our scored links, and shows no win rates; the agreed demo (part 7) is tracer, map and scoreboard. Investigate what the tab shows, explain it to the owner, and fix it as part of plan step 6 (graph and scoreboard from our own scores), unless the owner reprioritizes.

## Notes

Diagnosis 2026-10-03: frontend/components/influence-network.tsx draws, for ONE selected amendment, a star: left = organizations with a LobbyPlag 2013 historically verified link (backend services/demo.py graph()), centre = the amendment, right = its MEP authors. Only 144 of 4,867 amendments (3.0%) have any verified link (113 with one, 31 with two), so 97% show no organizations. It uses none of our scores and cannot show who wins. Architecture fix (parts 5 and 7): one graph across the law built from our scored links (organizations, MEPs, amendments), with win rates and a scoreboard; depends on step 1's saved scores and evidence.
