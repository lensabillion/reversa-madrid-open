---
type: is
id: is-01m3yyx1v4mmxwvqzk0rvnptn3
title: "R2: Remove assumed-negative contamination and reconcile proposal versus document labels"
kind: task
status: closed
priority: 1
version: 4
delegate: null
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
hold: null
hold_until: null
created_at: 2026-10-02T18:44:23.012Z
updated_at: 2026-10-03T08:52:04.972Z
started_at: 2026-10-02T18:51:01.952Z
closed_at: 2026-10-03T08:52:04.971Z
close_reason: "Addressed on main by PR #20 (merged 4185f3b): practice labels come only from LobbyPlag's records, no negative is invented, unreviewed candidates (1,685) stay unlabelled and excluded, and no identical inputs carry opposite labels (backend/evaluation/README.md)."
resolution: null
duplicate_of: null
---
High. practice.py:80-94 labels 200 never-flagged same-article pairs negative; evaluate.py:77-83 trains on all 475 rows. Audit found two identical-input groups with contradictory labels in redline mode (6 rows) and three in paper mode (8 rows). Example: verified Bits of Freedom ITRE 387 has the same old/new model input as synthetic-negative LIBE 940. In paper mode ITRE 247 is positive and negative against two proposals from the same document, while retrieval supplies the same document passage. Using the same 5 folds and seed-0 2000 draws, logistic paper results change from P20 .9068 / recall .6454 / AUC .8718 to .9389 / .8085 / .8905 when synthetic rows are excluded from fitting. Fix the unit of labelling, keep unreviewed pairs unknown, and deduplicate inputs before training. This sensitivity run is not an unbiased new benchmark.

## Notes

Astra independently reconstructed 475 rows as 467 unique amendment/document pairs; one exact amendment/document pair has both labels. In redline mode identical text need not imply identical historical provenance; the contradiction means the present input features cannot identify the target, not proof every historical label is wrong. R2 sensitivity uses identical folds and seed-0 draws; do not treat it as an unbiased replacement benchmark.
