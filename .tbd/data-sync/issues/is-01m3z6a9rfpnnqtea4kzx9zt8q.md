---
type: is
id: is-01m3z6a9rfpnnqtea4kzx9zt8q
title: Evaluate semantic influence scoring against the current lexical baseline
kind: feature
status: in_progress
priority: 1
version: 3
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T20:53:57.135Z
updated_at: 2026-10-02T21:12:43.675Z
started_at: 2026-10-02T20:54:15.247Z
---
User reports backend too weak. Establish a reproducible current-backend evaluation with trustworthy public label provenance, leakage-aware split contract, explicit unknown labels and challenging legal diagnostic cases. Assess a pinned pretrained semantic scorer against lexical baseline, retaining model inputs/revision, evidence, failures and metrics. Do not claim calibrated probabilities or hidden-test accuracy without independent labels. Document measured results and concrete implementation decisions; preserve separate adoption task.

## Notes

PR #14 https://github.com/lensabillion/reversa-madrid-open/pull/14 commit a322b92 adds frozen lexical diagnostics and isolated pinned Qwen3 reranker experiment. Preferred ordering 2/10 lexical versus 8/10 Qwen on synthetic cases only; model not promoted due quantity/modality failures and high decoy scores. Full make check passes: 110 backend tests, 100% production coverage, 33 frontend tests, build; runtime strict checks and both backend locks audit clean. Independent review reproduced lexical results and checked recorded logits. Methodology, raw outputs, failures and reproduction in backend/evaluation/README.md; continuation in docs/implementation-status.md. GitHub checks not yet reported; remain open pending CI and merge.
