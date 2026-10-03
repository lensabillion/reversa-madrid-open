---
type: is
id: is-01m40vj7z45gqkxyfbkfxmwgs5
title: "Part 3 · Shortlist the union of delta and whole-text BM25 queries (recall@5 0.82 -> 0.98 on LobbyPlag, PR #41)"
kind: feature
status: open
priority: 0
version: 1
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-03T12:24:31.972Z
updated_at: 2026-10-03T12:24:31.972Z
---
pipeline.find_candidates uses the delta query only at k=5 (recall@5 0.82 in backend/evaluation/fused-retrieval.json); the union of delta and whole-text top-5 reached 0.98 at ~6.5 candidates per amendment. Adopt it with before/after evidence and the assess_link cost. Branch feat/candidate-union (subagent, 2026-10-03).
