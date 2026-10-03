---
type: is
id: is-01m40fgfhe8qaj6srfqh1r6ada
title: "Part 6 · Atlas graph: actor -> ask -> amendment -> final article, plus MEPs, topics, years, meetings and votes, every edge with evidence"
kind: feature
status: in_progress
priority: 0
version: 10
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
updated_at: 2026-10-03T10:37:13.597Z
started_at: 2026-10-03T10:00:59.971Z
---
Atlas part 6. Built only from part 4's published links and part 5's outcomes, never from LobbyPlag labels. Store as plain files (JSONL/Parquet) per law plus one merged index; each edge carries its evidence record id. Serves the explorer, rankings and report. NetworkX for analysis; no graph database unless measured need.

## Notes

2026-10-03 main check: CONTRACT BLOCKER RESOLVED. PR25 https://github.com/lensabillion/reversa-madrid-open/pull/25 merged at c5365dc; all 9 CI checks passed. atlas-1 provides shared records, GraphSnapshot, exact SourceSpan rules and generated two-law consumer fixtures covering supported/opposite/short-edit/ambiguous/missing-date/missing-final/partial cases. Graph projection and ranking calculations can now be built/tested against these fixtures; real pipeline remains pending (Agent1 draft PR26, Agent2 outputs). PR24 presentation at933385a remains open. Next integration must handle insufficient_evidence status, span offsets relative to each record field, and separate heard/parliament_position/final_act outcomes; keep unknown separate and all observed asks including unmatched asks for coverage. No backend graph service implemented yet. Fetched main only; current feat/atlas-explorer checkout and local synthetic preview on port3013 preserved.
