---
type: is
id: is-01m3z6a9rfpnnqtea4kzx9zt8q
title: Evaluate semantic influence scoring against the current lexical baseline
kind: feature
status: in_progress
priority: 1
version: 4
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T20:53:57.135Z
updated_at: 2026-10-02T21:15:26.465Z
started_at: 2026-10-02T20:54:15.247Z
---
User reports backend too weak. Establish a reproducible current-backend evaluation with trustworthy public label provenance, leakage-aware split contract, explicit unknown labels and challenging legal diagnostic cases. Assess a pinned pretrained semantic scorer against lexical baseline, retaining model inputs/revision, evidence, failures and metrics. Do not claim calibrated probabilities or hidden-test accuracy without independent labels. Document measured results and concrete implementation decisions; preserve separate adoption task.

## Notes

PR #14 https://github.com/lensabillion/reversa-madrid-open/pull/14 ready for review at 6f8be7a after merging main and resolving documentation overlap. All nine GitHub CI checks passed; gh pr checks --watch exited 0. Final make check: 110 backend tests, 100% production coverage (475 statements,104 branches),38 frontend tests,production build,all audits clean. Optional runtime strict typing/Ruff and 54-package audit pass. Frozen synthetic ordering: lexical2/10,Qwen8/10; not influence accuracy or production promotion. Raw scores/model revision/fixture hashes/failures/reproduction in backend/evaluation/README.md and JSON; continuation in docs/implementation-status.md. Independent review found no blockers. Remains open until merge.
