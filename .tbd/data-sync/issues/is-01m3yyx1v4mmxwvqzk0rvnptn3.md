---
type: is
id: is-01m3yyx1v4mmxwvqzk0rvnptn3
title: "R2: Remove assumed-negative contamination and reconcile proposal versus document labels"
kind: task
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
created_at: 2026-10-02T18:44:23.012Z
updated_at: 2026-10-02T18:44:23.012Z
---
High. practice.py:80-94 labels 200 never-flagged same-article pairs negative; evaluate.py:77-83 trains on all 475 rows. Audit found two identical-input groups with contradictory labels in redline mode (6 rows) and three in paper mode (8 rows). Example: verified Bits of Freedom ITRE 387 has the same old/new model input as synthetic-negative LIBE 940. In paper mode ITRE 247 is positive and negative against two proposals from the same document, while retrieval supplies the same document passage. Using the same 5 folds and seed-0 2000 draws, logistic paper results change from P20 .9068 / recall .6454 / AUC .8718 to .9389 / .8085 / .8905 when synthetic rows are excluded from fitting. Fix the unit of labelling, keep unreviewed pairs unknown, and deduplicate inputs before training. This sensitivity run is not an unbiased new benchmark.
