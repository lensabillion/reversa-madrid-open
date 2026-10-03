---
type: is
id: is-01m3yxjrzde6r6gw3jfr2e85bz
title: "Part 1 · Collect: influence collect <procedure> downloads and normalizes one law's public record"
kind: feature
status: in_progress
priority: 0
version: 16
delegate: claude-code@vm
labels: []
dependencies:
  - type: blocks
    target: is-01m3z9e7eesds3s8v38tswk2p6
  - type: blocks
    target: is-01m40fgh7rr8spaqfeat0v6qzm
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T18:21:17.677Z
updated_at: 2026-10-03T15:27:50.200Z
started_at: 2026-10-02T18:21:17.985Z
---
CLI: influence load <law>. Sources: Have Your Say API (feedback + attachment PDFs as text), Parltrack committee amendments dump, Publications Office (CELLAR) texts of Parliament's position and the final act. Output under data/laws/<law>/ as JSONL + text with provenance. Start with the AI Act (2021/0106(COD)).

## Notes

Review-sweep fixes in PR https://github.com/lensabillion/reversa-madrid-open/pull/72 (17:30, 3 Oct).
