---
type: is
id: is-01m40fgh1nsehehafndm6xy85d
title: "D1: decide the language-model judge for part 4 (none, local open model, Claude, Jev) on practice-loop evidence"
kind: task
status: in_progress
priority: 1
version: 7
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T08:53:52.821Z
updated_at: 2026-10-03T14:16:27.341Z
started_at: 2026-10-03T12:01:03.578Z
---
Open decision D1. Under the Atlas brief the judge runs on thousands of candidates, not 60 pairs, so cost and speed matter; a local model needs no key and no approval to send text. Measure each option on LobbyPlag folds and the blind audit before adopting.

## Notes

Draft PR #63: https://github.com/lensabillion/reversa-madrid-open/pull/63 (commit cba37cf), based on main cb9c299. Jev adapter, budget/cache runner, 19-feature grouped comparison, provenance-bound calculation integration and optional atlas view wiring implemented. Full make check passed: 1188 backend/benchmark tests, 100% application branch coverage (6434 statements/1640 branches), 94 frontend tests, build, catalogs and both audits. Nine PR checks pending. Jev synthetic24/24 vs local17/24. Full15signal baseline P20 .9727/AUC .9230/recall .8510; +4Jev .9561/.9516/.8567: no production promotion. Both941case real trials complete; contextcoverage253→817. Same .58 diagnostic cutoff leaves388 in each; original10agentreview still2 supported,7 unestablished,1 unresolved. Total accounted USD .136191594 includes retained failed-save reservation. Gate3 remains open (live0published); CLI artifact loading, frozen deployable model and real-prose precision policy remain. No manual score edits or blanket prose override. Repository status and evaluation JSON preserve evidence.
