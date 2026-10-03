---
type: is
id: is-01m3z9e78mr2xgekmtcx1vk5t2
title: "Plan step 2: practice harness on main (precision in top 20, recall, AUC on simulated 30+30 tests)"
kind: feature
status: in_progress
priority: 0
version: 3
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T21:48:31.379Z
updated_at: 2026-10-03T08:21:25.037Z
started_at: 2026-10-02T21:53:43.811Z
---
Architecture practice loop. Labelled LobbyPlag pairs with provenance (verified = positive; crowd-rejected = weak negative, R1; no synthetic same-article negatives, R2), folds that keep each lobby organization and each amendment out of its own training data (R4), paired 30+30 draws with random tie-breaking and a printed seed, reported for main's lexical scorer and LobbyPlag's stored match. Every later scorer change reports before and after here. Covers rev-ol2g, rev-aekp, rev-p2rd.

## Notes

PR #20 opened 2026-10-03 (feat/practice-harness). Code by delegated agent (stopped on session limit, uncommitted); coordinator reviewed every module, fixed a fold-fallback bug found by Hypothesis (regression test added), renamed TestSettings to SimulationSettings, wrote harness and CLI tests, documented results. make check exit 0: 161 backend tests, 100% coverage of 829 statements/182 branches. Lexical P@20 0.980, recall 0.814, AUC 0.863; per-fold AUC 0.655-0.987. Close when merged.
