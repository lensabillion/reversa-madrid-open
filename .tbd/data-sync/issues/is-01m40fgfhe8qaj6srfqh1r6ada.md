---
type: is
id: is-01m40fgfhe8qaj6srfqh1r6ada
title: "Part 6 · Atlas graph: actor -> ask -> amendment -> final article, plus MEPs, topics, years, meetings and votes, every edge with evidence"
kind: feature
status: in_progress
priority: 0
version: 13
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
updated_at: 2026-10-03T11:14:50.707Z
started_at: 2026-10-03T10:00:59.971Z
---
Atlas part 6. Built only from part 4's published links and part 5's outcomes, never from LobbyPlag labels. Store as plain files (JSONL/Parquet) per law plus one merged index; each edge carries its evidence record id. Serves the explorer, rankings and report. NetworkX for analysis; no graph database unless measured need.

## Notes

Agent 3 graph consumer against atlas-1, worktree atlas-calculations, branch feat/atlas-graph-analysis. PR https://github.com/lensabillion/reversa-madrid-open/pull/28 now at 4072245 after main bdb0c61/PR26 merge; all9 CI checks green. No code conflicts, both docs sections retained and historical handoff claims clarified. Pure graph service validates published joins/quotes/chronology, preserves joint attribution, coverage and deterministic IDs; audit candidates excluded, conflicting IDs/results rejected. Fixture11nodes/9edges/2published links/1final realization, not real findings. make check passes538 backend tests,100%coverage3349 statements/844branches,37frontend tests/build,6catalogs,both audits. Agent1 handoff still requires collect/API/CLI orchestration and amendment document_id/source provenance fix; graph validation not weakened. Parent owns frontend integration. Keep open pending merge and real integration.
