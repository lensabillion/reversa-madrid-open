---
type: is
id: is-01m3yyx26p8qcfzkhq74n8b2f6
title: "R4: Strengthen grouped evaluation and document model-selection uncertainty"
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
created_at: 2026-10-02T18:44:23.382Z
updated_at: 2026-10-03T08:52:05.143Z
started_at: 2026-10-02T18:51:02.118Z
closed_at: 2026-10-03T08:52:05.142Z
close_reason: "Addressed on main by PR #20 (merged 4185f3b): folds keep every organization, amendment text and submission text on one side; per-fold results reported (AUC 0.655-0.987); identical seeded draws across scorers. Residual multilingual/paraphrase held-out cases move to the Atlas audit bead."
resolution: null
duplicate_of: null
---
High. evaluate.py:46-55 groups only by lobbyist; 103/475 held-out rows reuse a training amendment and 18/175 positive rows reuse an exact positive submission change from training. IDF corpus.py:93-97 also includes all practice texts. All 4867 amendment records are English and from GDPR. Repeated 30+30 draws are from the same OOF predictions, not independent new-law validation. Prevent duplicated amendment/passage components crossing folds; explicitly declare transductive IDF or fit preprocessing only on train; freeze model selection separately; report per-fold/organization results and obtain held-out paraphrase/multilingual cases. Headline redline result is the blend (.9985/.8166/.9275); paper result is logistic (.9068/.6454/.8718), so label model identities.

## Notes

Independent Astra review: score pooling mixes predictions from five separately fitted models, so cross-fold score-scale shifts affect P20/AUC. Resampled subsets are not independent deployments. Original scorer loop advances one RNG across models, so comparisons are not paired; use identical draws. Amendment overlap is a generalization risk, not proof of a specific inflation amount. Unsupervised IDF transduction is distinct from supervised overlap.
