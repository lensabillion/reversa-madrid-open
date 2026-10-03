---
type: is
id: is-01m40s303dwm7jrhw8vktxgez0
title: Complete consolidated-plan signal calculation and evaluation
kind: task
status: in_progress
priority: 0
version: 3
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-03T11:41:15.245Z
updated_at: 2026-10-03T12:43:45.350Z
started_at: 2026-10-03T11:41:31.110Z
---
User explicitly requests complete calculation per docs/plan.md, no omitted signals. Extend Agent2 assessment/outcome branches rather than duplicate them. Scope: requirement coverage matrix, measured semantic retrieval, rarity/alignment/background/mutual/legal signals, fitted grouped combiner and threshold evidence, integration/handoff. No unapproved external judge/API spending; no probability/publication claims without evaluation.

## Notes

PR #48 https://github.com/lensabillion/reversa-madrid-open/pull/48 implements and evaluates fitted signals/local models; all nine CI checks pass at9c15f42. Main through2fbb229 integrated; full local gate941backend100%branch and94frontend tests. No fitted model promoted: baselineP20.9801 vsdeterministic/background.9765,Qwen+NLI.9671,E5+NLI.9718. Current work is real AIAct end-to-end and Gate3 acceptance (20published links/10randomread), with3subagents. Proper systemCA trust fixed HYS fetch; full attachments run active. Gate7 independent40link/twohuman audit is later and not claimed.
