---
type: is
id: is-01m40fgfhe8qaj6srfqh1r6ada
title: "Part 6 · Atlas graph: actor -> ask -> amendment -> final article, plus MEPs, topics, years, meetings and votes, every edge with evidence"
kind: feature
status: in_progress
priority: 0
version: 11
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
updated_at: 2026-10-03T10:41:36.237Z
started_at: 2026-10-03T10:00:59.971Z
---
Atlas part 6. Built only from part 4's published links and part 5's outcomes, never from LobbyPlag labels. Store as plain files (JSONL/Parquet) per law plus one merged index; each edge carries its evidence record id. Serves the explorer, rankings and report. NetworkX for analysis; no graph database unless measured need.

## Notes

Implementation started against merged atlas-1 at c5365dc. Backend isolated worktree atlas-calculations branch feat/atlas-graph-analysis; graph subagent owns services/atlas_graph.py and test, rankings subagent owns services/atlas_analysis.py and test under rev-5yy6. Parent owns integration/docs/gates. UI feat/atlas-explorer merged main and adapter subagent consumes shared fixtures. Services have no HTTP/dependencies/shared-schema changes. Need deterministic joins/exact spans/publication boundary; per actor-stage distinct asks, including unmatched requests; assessed denominator excludes unknown; same-result repeated outcomes count once; conflicting classifications error. Procedure year is canonical procedure-reference year in both backend and UI. Real collection/scoring integration remains pending Agent1/2.
