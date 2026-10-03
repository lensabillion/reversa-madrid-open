---
type: is
id: is-01m40s303dwm7jrhw8vktxgez0
title: Complete consolidated-plan signal calculation and evaluation
kind: task
status: in_progress
priority: 0
version: 6
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-03T11:41:15.245Z
updated_at: 2026-10-03T14:16:27.536Z
started_at: 2026-10-03T11:41:31.110Z
---
User explicitly requests complete calculation per docs/plan.md, no omitted signals. Extend Agent2 assessment/outcome branches rather than duplicate them. Scope: requirement coverage matrix, measured semantic retrieval, rarity/alignment/background/mutual/legal signals, fitted grouped combiner and threshold evidence, integration/handoff. No unapproved external judge/API spending; no probability/publication claims without evaluation.

## Notes

PR48 remains merged. Follow-up draft PR63 https://github.com/lensabillion/reversa-madrid-open/pull/63 integrates Jev with existing deterministic, rarity, alignment, operation, legal-cue, background/rank and semantic features in one fitted calculation and optional pipeline.build_view path through outcomes/graph/rankings/API. Combined19feature integration tests prove semantic and Jev values independently affect the same support score and missing features fail. Full make check1188 backend+benchmark tests100%,94frontend passed. Maincb9c299 default CLI still lexical; no validated fit/publication policy enabled. Full-signal +Jev AUC improves .9230→.9516 but P20 drops .9727→.9561. Real diagnostic review still fails; Gate3 NOT complete. Required next work: freeze actual deployable model/corpus/feature and context policy; measured real-prose precision, complete source background beyond target provision, safe CLI artifacts then actual20published+10random reads. Gate7 independent human audit separate. Cost/evidence/limitations in docs/implementation-status.md and backend/evaluation/*jev*.json.
