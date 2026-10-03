---
type: is
id: is-01m3z9e7eesds3s8v38tswk2p6
title: "Part 3 · Find candidates: per-law index over amendment changes and submission passages, shortlist per amendment"
kind: feature
status: open
priority: 0
version: 4
labels: []
dependencies:
  - type: blocks
    target: is-01m40fgfbf2anx19zzzv3y9bqy
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T21:48:31.565Z
updated_at: 2026-10-03T08:54:02.646Z
---
Pick the passages of a long submission that match the amendment's change, keep alternatives and offsets, bound repeated-term credit (R7), and lift the scorer's 800-token limit for whole papers without silent truncation. Measure with the practice harness on whole papers. Depends on step 2.

## Notes

2026-10-03, Atlas re-plan (rev-sz6q): retargeted to Atlas part 3. Absorbs the passage finder: whole papers are split into passages, and every amendment's change is searched against every passage of the law's submissions (lexical BM25-style plus multilingual embeddings), keeping the top-k with offsets and alternatives. Measure retrieval recall on LobbyPlag (does the verified passage reach the shortlist?) before tuning part 4. R7 (rev-00x6) applies.
