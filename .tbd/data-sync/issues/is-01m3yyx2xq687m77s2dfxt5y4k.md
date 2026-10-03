---
type: is
id: is-01m3yyx2xq687m77s2dfxt5y4k
title: "R8: Choose the publication threshold that keeps shown links high-precision, and the fallback when a signal fails"
kind: task
status: in_progress
priority: 1
version: 6
delegate: claude-code@dani
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
hold: null
hold_until: null
created_at: 2026-10-02T18:44:24.118Z
updated_at: 2026-10-03T11:53:18.397Z
started_at: 2026-10-02T18:51:02.290Z
---
High. evaluate.py:50 reweights training to 50/50 and predict_proba is used without a calibration fit. Recall assumes threshold .5 at line 40; organizer threshold is still unresolved in rev-qvmx. Primer:440 incorrectly infers that a balanced test implies half of scores should exceed .5. Primer:489 promises judge/translation fallback without a validated fallback model. Confirm scoring contract, calibrate on separate grouped data if probabilities are claimed, evaluate every available-signal configuration, and record degraded runs. Escalate missing required input rather than inventing a confidence score.

## Notes

Independent Astra review: class balancing is reasonable for a known 50/50 target prevalence and is not itself a defect. The issues are unsupported calibration language, an unresolved .5 recall threshold, the false implication that half of scores should exceed .5, and unevaluated fallback behavior.

2026-10-03, Atlas re-plan (rev-sz6q): the hidden test and its recall threshold are gone. The jury reads 3 random published links; P(all 3 real) = p^3, so the target is precision of what we show (for example 0.95 gives 0.86). Choose the threshold on LobbyPlag folds and a blind audit sample of our own 2019+ links, report a Wilson interval, and record which signals were available per link.
