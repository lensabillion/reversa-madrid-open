---
type: is
id: is-01m40fgfhe8qaj6srfqh1r6ada
title: "Part 6 · Atlas graph: actor -> ask -> amendment -> final article, plus MEPs, topics, years, meetings and votes, every edge with evidence"
kind: feature
status: in_progress
priority: 0
version: 12
delegate: codex@lensas-macbook-air.local
labels: []
dependencies:
  - type: blocks
    target: is-01m40fgfqa8b905kamgqhmmsjd
  - type: blocks
    target: is-01m40fgg3kvg514bax9q3zyhwy
  - type: blocks
    target: is-01m40fgg9kpb0xpqjmkwqp8pm9
parent_id: is-01m3ygrva6wcq297g7j12g99c2
child_order_hints:
  - is-01m40m06dz2jynxdvbrydqr03z
  - is-01m40m9petsrdhjvg47v8nx85f
hold: null
hold_until: null
created_at: 2026-10-03T08:53:51.277Z
updated_at: 2026-10-03T11:06:39.579Z
started_at: 2026-10-03T10:00:59.971Z
---
Atlas part 6. Built only from part 4's published links and part 5's outcomes, never from LobbyPlag labels. Store as plain files (JSONL/Parquet) per law plus one merged index; each edge carries its evidence record id. Serves the explorer, rankings and report. NetworkX for analysis; no graph database unless measured need.

## Notes

Agent 3 graph consumer implemented against merged atlas-1 in isolated atlas-calculations worktree, branch feat/atlas-graph-analysis. PR https://github.com/lensabillion/reversa-madrid-open/pull/28 at cac0f29; all 9 CI checks passed. Pure services/atlas_graph.py preserves published actor/request/amendment paths and supported final outcomes, exact quotes, chronology, joint attribution, coverage and deterministic IDs. Rejects conflicting IDs/results and invalid published joins; audit candidates cannot become public paths. Synthetic fixture only: 11 nodes, 9 edges, 2 published origin links and 1 final realization. make check passed: 274 backend tests, 100% coverage (1563 statements/390 branches), 37 frontend tests/build, 6/6 catalogs, both audits clean. No shared schema/API/CLI/dependency changes. Real Agent1/2 pipeline and UI integration remain pending; do not close broader graph work from fixture success. Parent owns integration and frontend branch.
