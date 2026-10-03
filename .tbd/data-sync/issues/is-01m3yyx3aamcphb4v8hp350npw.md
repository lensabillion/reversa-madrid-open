---
type: is
id: is-01m3yyx3aamcphb4v8hp350npw
title: "Part 7 · Forecast: who is rising and which open asks will land, tested on laws decided later than the training laws"
kind: task
status: in_progress
priority: 1
version: 5
delegate: claude-code@dani
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
hold: null
hold_until: null
created_at: 2026-10-02T18:44:24.521Z
updated_at: 2026-10-03T11:53:18.403Z
started_at: 2026-10-03T11:53:18.403Z
---
High readiness gap. primer:323-339 lists plausible adoption predictors but no fitted adoption model, proposal-to-final-law labels, temporal evaluation or measured AUC exists in current code. War of Words II catalog datasets.yaml:964-979 is committee-edit acceptance, not consultation-proposal final adoption. Existing rev-uhpq concerns retrospective text survival and cannot by itself validate forecasting. Define proposal-level outcome, partial adoption and timestamp, freeze eligible inputs, and build/evaluate the simplest adoption baseline before adding graph-derived predictors. Clarifications are already tracked in rev-qvmx.

## Notes

Adoption label decided 2026-10-03 (see rev-e5xh): text survival in the final GDPR. Forecast cutoff and the use of final-law text as an input at 19:00 remain open under D5 (rev-qvmx).

2026-10-03, Atlas re-plan (rev-sz6q): no proposals.csv or AUC from organizers. Train on procedures concluded before a cutoff, test on later ones (time split), report AUC/Brier on that split, then apply to procedures under negotiation now. Rising/fading = trend in wins per actor and topic by year. Inputs: part 5 outcomes, part 6 graph features (support breadth, coalition size, actor type, rapporteur meetings).
