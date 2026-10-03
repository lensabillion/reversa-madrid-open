---
type: is
id: is-01m40fgh1nsehehafndm6xy85d
title: "D1: decide the language-model judge for part 4 (none, local open model, Claude, Jev) on practice-loop evidence"
kind: task
status: in_progress
priority: 1
version: 6
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T08:53:52.821Z
updated_at: 2026-10-03T13:57:56.683Z
started_at: 2026-10-03T12:01:03.578Z
---
Open decision D1. Under the Atlas brief the judge runs on thousands of candidates, not 60 pairs, so cost and speed matter; a local model needs no key and no approval to send text. Measure each option on LobbyPlag folds and the blind audit before adopting.

## Notes

Jev trial authorized and running under cumulative USD1 cap. Adapter tests46 and full backend1131 passed100%branchcoverage on main cb9c299. Pilot24/24 vs local17/24. Public272pair inference complete with222 unique requests; lexical+Jev limited comparison improved AUC/recall but reduced P@20. User clarified all planned signals must be considered. Extending existing calculation_plan benchmark with deterministic rarity/alignment/operation/legal cues, background/mutual ranks, Qwen semantic cosine and four separate Jev signals (19 features), plus provenance-bound optional Jev inputs in existing calculation service. No blanket prose publication or manufactured Gate3 pass. Full941 saved AI Act candidate diagnostic ongoing; raw outputs and random agent review separate from human audit. Actual artifacts under primary data/jev-evaluation; branch feat/jev-gate-three.
