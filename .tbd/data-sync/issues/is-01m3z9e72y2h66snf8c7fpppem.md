---
type: is
id: is-01m3z9e72y2h66snf8c7fpppem
title: "Plan step 1: submission command that scores supplied pairs and writes a validated pairs.csv"
kind: feature
status: in_progress
priority: 0
version: 4
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T21:48:31.197Z
updated_at: 2026-10-03T08:14:47.488Z
started_at: 2026-10-02T21:51:38.238Z
---
Architecture parts 1-4 wired into one command (see .agents/skills/influence-architecture). Read a normalized pairs input (JSON Lines; the organizers' format gets an adapter once D5 is answered), score each pair with the existing comparison service, write pairs.csv (pair_id,influence_score) atomically after validating exactly the input IDs, uniqueness and finite scores in [0,1], and save each score's evidence. Rehearse on 60 LobbyPlag pairs against a timer. Part of rev-fkut (R11).

## Notes

PR #19 opened 2026-10-03 (feat/submission-command). Code by delegated agent (stopped on session limit before opening the PR); reviewed line by line by the coordinator. make check exit 0: 143 backend tests, 100% coverage of 666 statements/142 branches; make submit reproduces the golden pairs.csv; invalid input exits 1 and leaves the previous pairs.csv; 60-pair LobbyPlag rehearsal 0.16 s per command on Apple M5. Close when merged.
