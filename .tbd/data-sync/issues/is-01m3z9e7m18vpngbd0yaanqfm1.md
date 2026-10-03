---
type: is
id: is-01m3z9e7m18vpngbd0yaanqfm1
title: "Plan step 4: adoption baseline writing proposals.csv from the same command (architecture part 6)"
kind: feature
status: open
priority: 1
version: 2
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T21:48:31.745Z
updated_at: 2026-10-03T08:25:05.641Z
---
Define what counts as adopted and the forecast cutoff first (R10, rev-104q) and agree it with the owner; then a small loader for one law's consultation and final text (replaces the deleted feat/law-loader; facts in rev-pjk2), and the simplest measured adoption model with AUC.

## Notes

Owner decision 2026-10-03: 'adopted' = the wording a consultation proposal asked for survives in the final GDPR (text survival, automatic labels, no hand labelling). Data: LobbyPlag's 1,159 GDPR proposals (old/new wording, target article) and the final GDPR (data/eurlex/32016R0679.xhtml), both local. Model: small logistic regression on support from part 4's links (amendments echoing the proposal, their scores), AUC on organization-grouped folds in the practice harness (#20). Needs the step 3 passage finder to locate each proposal's passage in the final law. Record in the Decisions table in the step 4 PR. Rejected: AI Act HYS (free text, needs loader, more hours); untrained rule (weaker).
