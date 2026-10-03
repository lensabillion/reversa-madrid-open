---
type: is
id: is-01m3z9e7eesds3s8v38tswk2p6
title: "Part 3 · Find candidates: per-law index over amendment changes and submission passages, shortlist per amendment"
kind: feature
status: in_progress
priority: 0
version: 8
delegate: claude-code@dani
labels: []
dependencies:
  - type: blocks
    target: is-01m40fgfbf2anx19zzzv3y9bqy
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T21:48:31.565Z
updated_at: 2026-10-03T11:53:22.903Z
started_at: 2026-10-03T09:58:40.190Z
---
Pick the passages of a long submission that match the amendment's change, keep alternatives and offsets, bound repeated-term credit (R7), and lift the scorer's 800-token limit for whole papers without silent truncation. Measure with the practice harness on whole papers. Depends on step 2.

## Notes

2026-10-03 Agent 2: BM25 passage retrieval pushed on feat/candidate-retrieval (PR not yet opened: gh missing locally). Mechanics tested, 100% coverage. Recall@k on LobbyPlag NOT yet measured; next. 2 pre-existing Windows-only test failures (CRLF golden, os.replace).

2026-10-03 13:25 CEST, state of main at bdb0c61 (recorded by cloud session claude/eloquent-allen-jbxbmy): PR #27 merged 12:53 (dpmaturana): services/retrieval.py + schemas/retrieval.py, BM25 over submission passages; the query is the amendment's changed words, or the whole text when the original is unknown. Gaps against the plan and contract: uses its own SourcePassage/PassageCandidate/Shortlist instead of atlas Passage/Candidate; its split_passages (non-overlapping, <=120 tokens) duplicates services/passages.py (1-3 overlapping sentences, atlas Passage, PR #26), so converge on one splitter; recall@20 on LobbyPlag not measured (plan gate 2); no dense retriever yet.

2026-10-03 Agent 2: PR #27 (BM25 retrieval) and PR #29 (services/passage_change.py: a quoted instruction such as replace 'shall' with 'may' becomes an old/new change with exact offsets; prose stays a statement with an unknown original) are merged. PR #35 measures recall@k on LobbyPlag's 172 verified pairs: recall@20 0.750 when proposals are indexed by new wording only, 0.913 when a deletion proposal is indexed by the wording it deletes (same queries); on the 139 pairs where both queries run, whole-text 0.978 vs changed-words 0.899 at @20. Optimistic by construction (LobbyPlag's own matcher proposed every candidate), one law, precision of the shortlist not measured. A fused-retriever follow-up is in progress.
