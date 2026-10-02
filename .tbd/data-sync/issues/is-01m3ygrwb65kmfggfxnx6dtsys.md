---
type: is
id: is-01m3ygrwb65kmfggfxnx6dtsys
title: Decide whether to keep or discard the uncommitted prototype in influence/
kind: chore
status: open
priority: 2
version: 3
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T14:37:26.246Z
updated_at: 2026-10-02T21:49:05.064Z
---
A prototype matcher (text.py, corpus.py, features.py, embed.py, practice.py, evaluate.py) was written before the design was agreed. It scored P@20 1.00 / recall 0.82 on LobbyPlag redlines and P@20 0.91 / recall 0.65 on full-paper submissions. Keep only what fits the agreed design.

## Notes

Decided by the owner 2026-10-02: the attic prototype predates the architecture and is not built on (D3 row in docs/implementation-status.md, PR #16). Close when #16 merges.
