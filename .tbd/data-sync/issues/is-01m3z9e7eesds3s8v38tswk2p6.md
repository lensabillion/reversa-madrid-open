---
type: is
id: is-01m3z9e7eesds3s8v38tswk2p6
title: "Part 3 · Find candidates: per-law index over amendment changes and submission passages, shortlist per amendment"
kind: feature
status: in_progress
priority: 0
version: 6
delegate: claude-code@dani
labels: []
dependencies:
  - type: blocks
    target: is-01m40fgfbf2anx19zzzv3y9bqy
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T21:48:31.565Z
updated_at: 2026-10-03T10:04:21.067Z
started_at: 2026-10-03T09:58:40.190Z
---
Pick the passages of a long submission that match the amendment's change, keep alternatives and offsets, bound repeated-term credit (R7), and lift the scorer's 800-token limit for whole papers without silent truncation. Measure with the practice harness on whole papers. Depends on step 2.

## Notes

2026-10-03 Agent 2: BM25 passage retrieval pushed on feat/candidate-retrieval (PR not yet opened: gh missing locally). Mechanics tested, 100% coverage. Recall@k on LobbyPlag NOT yet measured; next. 2 pre-existing Windows-only test failures (CRLF golden, os.replace).
