---
type: is
id: is-01m40fgfhe8qaj6srfqh1r6ada
title: "Part 6 · Atlas graph: actor -> ask -> amendment -> final article, plus MEPs, topics, years, meetings and votes, every edge with evidence"
kind: feature
status: in_progress
priority: 0
version: 9
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
updated_at: 2026-10-03T10:20:54.787Z
started_at: 2026-10-03T10:00:59.971Z
---
Atlas part 6. Built only from part 4's published links and part 5's outcomes, never from LobbyPlag labels. Store as plain files (JSONL/Parquet) per law plus one merged index; each edge carries its evidence record id. Serves the explorer, rankings and report. NetworkX for analysis; no graph database unless measured need.

## Notes

Agent 3 active in feat/atlas-explorer; PR24 https://github.com/lensabillion/reversa-madrid-open/pull/24 prepares evidence/explorer (rev-oodw). Subagent verified 2026-10-03: Agent1 published branch and main remain 0518f17; Agent2 d1cf813 exposes retrieval-only types. No frozen schemas/atlas.py, GraphSnapshot or fixtures available, so graph service not implemented. Required contract: canonical IDs/revision; sources and exact document-relative code-point quotes; chronology/publication flags; stage-specific outcomes including unmatched asks; coverage/run metadata; deterministic node/edge and audit shape. Graph must reject dangling/conflicting duplicate IDs, deduplicate identical paths, retain joint asks, allow published heard links with unknown final outcome. Frontend adapter must translate document-relative spans to excerpt-relative offsets. Pure build_graph service follows after handoff. Analysis/report display preparation delegated under rev-1jc4; real rankings/report/demo remain open.
