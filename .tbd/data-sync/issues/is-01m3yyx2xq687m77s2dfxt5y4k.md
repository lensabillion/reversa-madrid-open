---
type: is
id: is-01m3yyx2xq687m77s2dfxt5y4k
title: "R8: Define score calibration, recall threshold and evaluated fallback behavior"
kind: task
status: open
priority: 1
version: 3
delegate: null
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
hold: null
hold_until: null
created_at: 2026-10-02T18:44:24.118Z
updated_at: 2026-10-02T18:51:10.579Z
started_at: 2026-10-02T18:51:02.290Z
---
High. evaluate.py:50 reweights training to 50/50 and predict_proba is used without a calibration fit. Recall assumes threshold .5 at line 40; organizer threshold is still unresolved in rev-qvmx. Primer:440 incorrectly infers that a balanced test implies half of scores should exceed .5. Primer:489 promises judge/translation fallback without a validated fallback model. Confirm scoring contract, calibrate on separate grouped data if probabilities are claimed, evaluate every available-signal configuration, and record degraded runs. Escalate missing required input rather than inventing a confidence score.

## Notes

Independent Astra review: class balancing is reasonable for a known 50/50 target prevalence and is not itself a defect. The issues are unsupported calibration language, an unresolved .5 recall threshold, the false implication that half of scores should exceed .5, and unevaluated fallback behavior.
