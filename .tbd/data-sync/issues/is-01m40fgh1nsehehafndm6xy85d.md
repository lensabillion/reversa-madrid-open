---
type: is
id: is-01m40fgh1nsehehafndm6xy85d
title: "D1: decide the language-model judge for part 4 (none, local open model, Claude, Jev) on practice-loop evidence"
kind: task
status: in_progress
priority: 1
version: 3
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T08:53:52.821Z
updated_at: 2026-10-03T12:01:59.994Z
started_at: 2026-10-03T12:01:03.578Z
---
Open decision D1. Under the Atlas brief the judge runs on thousands of candidates, not 60 pairs, so cost and speed matter; a local model needs no key and no approval to send text. Measure each option on LobbyPlag folds and the blind audit before adopting.

## Notes

Owner explicitly approved local model evaluation, with no paid API. Pinned DeBERTa NLI scored 17/24 on separate synthetic legal diagnostics; not approved to publish. Raw outputs remain separate from labels. Full grouped scoring comparison and local-runtime reproducibility are in progress under rev-qs6i.
