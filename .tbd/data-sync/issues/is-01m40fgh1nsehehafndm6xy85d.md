---
type: is
id: is-01m40fgh1nsehehafndm6xy85d
title: "D1: decide the language-model judge for part 4 (none, local open model, Claude, Jev) on practice-loop evidence"
kind: task
status: in_progress
priority: 1
version: 10
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T08:53:52.821Z
updated_at: 2026-10-03T15:27:13.431Z
started_at: 2026-10-03T12:01:03.578Z
---
Open decision D1. Under the Atlas brief the judge runs on thousands of candidates, not 60 pairs, so cost and speed matter; a local model needs no key and no approval to send text. Measure each option on LobbyPlag folds and the blind audit before adopting.

## Notes

Draft PR63 https://github.com/lensabillion/reversa-madrid-open/pull/63 at cba37cfd4a3ba8993758c12e64e5821d75b939ac: all nine CI checks SUCCESS, verified with REST check-runs. Local make check1188 backend/benchmark tests,100% application branch coverage,94frontend,build,catalogs,audits passed. Jev24/24 synthetic; full19signal model AUC .9230→.9516 but P20 .9727→.9561. Both941case real trials completed. Contextcoverage253→817; diagnosticcutoff.58 pool388→388; original10agent review still2supported,7unestablished,1unresolved. Total accounted USD.136191594. Source-context hash binding and Philips guard fixed. No model promotion, no score edits, no blanketproseoverride. Gate3 OPEN: live0published; missing deployable model/context policy and real-prose precision. Gate7human audit separate. Full reproducible evidence and next scope in PR docs/implementation-status.md, README and backend/evaluation. Main unchanged; dirty primary checkout untouched.

2026-10-03 ~17:30 CEST: owner decided in chat to switch Jev on for Part 4 on the live path, on all top-5 candidates (~28k AI Act, est. $2-4). Implementation: rev-cja5 (branch feat/jev-judge), reusing PR #63's services/jev.py and its four questions. PR #63 itself conflicts with main (pipeline.py) and its FittedVerification path has no CLI loader.

2026-10-03 17:30 (Claude, PR #71 session): the shared data/laws/2021-0106-COD/atlas.json was overwritten at 17:14 by the atlas-calculations worktree with method_revision 'rules-3+jev-legal-change-v1', publishing 398 links (391 reworded-tier, 7 copied-tier). Its view limitations still say '(rules-3); only copied-tier links are published', because pipeline.LIMITATIONS is built from assessment's constants, not from the verifier actually used. If the fitted/Jev path lands, the limitation sentence must describe its real publication policy. The reworded tier has not met its precision floor (0.72 vs 0.80 on LobbyPlag).
