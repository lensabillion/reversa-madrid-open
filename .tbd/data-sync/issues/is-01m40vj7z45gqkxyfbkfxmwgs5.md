---
type: is
id: is-01m40vj7z45gqkxyfbkfxmwgs5
title: "Part 3 · Shortlist the union of delta and whole-text BM25 queries (recall@5 0.82 -> 0.98 on LobbyPlag, PR #41)"
kind: feature
status: in_progress
priority: 0
version: 3
delegate: claude-code@vm
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T12:24:31.972Z
updated_at: 2026-10-03T13:47:11.345Z
started_at: 2026-10-03T13:47:10.945Z
---
pipeline.find_candidates uses the delta query only at k=5 (recall@5 0.82 in backend/evaluation/fused-retrieval.json); the union of delta and whole-text top-5 reached 0.98 at ~6.5 candidates per amendment. Adopt it with before/after evidence and the assess_link cost. Branch feat/candidate-union (subagent, 2026-10-03).

## Notes

2026-10-03 15:30 CEST: union implemented on local feat/candidate-union (0cecc59, 12b3c2e). Re-measured on LobbyPlag (harness output byte-identical to committed JSON): recall@5 0.820 (delta top 5, 5.00 cand/amendment) -> 0.965 (union top 5, 6.55); 'whole text if new wording else delta' also 0.965 at 5.00 (owner decision, Proposed row). Cost on synthetic 5,660-amendment law: part 3 9.6->26.1 s (437 asks), 74.6->220.4 s (3,000 asks). Decision: land a precomputed-weight BM25 speedup first (prototype: union part 3 210 s -> 43 s at 3,000 asks, identical candidates), then stack the union. Found: backend/models/prepare_lobbyplag.py imports recall._build_index which no longer exists (recall.build_index).
