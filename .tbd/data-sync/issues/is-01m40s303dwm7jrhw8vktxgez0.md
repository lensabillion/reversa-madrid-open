---
type: is
id: is-01m40s303dwm7jrhw8vktxgez0
title: Complete consolidated-plan signal calculation and evaluation
kind: task
status: in_progress
priority: 0
version: 7
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-03T11:41:15.245Z
updated_at: 2026-10-03T14:19:56.113Z
started_at: 2026-10-03T11:41:31.110Z
---
User explicitly requests complete calculation per docs/plan.md, no omitted signals. Extend Agent2 assessment/outcome branches rather than duplicate them. Scope: requirement coverage matrix, measured semantic retrieval, rarity/alignment/background/mutual/legal signals, fitted grouped combiner and threshold evidence, integration/handoff. No unapproved external judge/API spending; no probability/publication claims without evaluation.

## Notes

PR48 merged; followup draftPR63 https://github.com/lensabillion/reversa-madrid-open/pull/63 at cba37cf has ALL NINE CI checks SUCCESS. One19feature fitted calculation now combines deterministic rarity/alignment/operation/legal cues,background/mutual ranks,Qwen semantic cosine,and4Jev signals; optional FittedVerification connects it to outcomes/graph/rankings/API. Missing features fail; fullsource context provenance checked. Local gate1188 backend/benchmark tests100% application branches,94frontend and allothergates passed. Combinedmodel improvesAUC butreducesP20; realagent review remains poor afterproposalcontextfix. DefaultCLI is still existingrules,live0published,Gate3 NOT complete. Required next: validated frozen fit/corpus/features/model/prompt/context policy, real-prose precision, safeCLIartifactloader, then actual20published+10randomreads. Gate7 independenthuman audit separate. All evidence/provenance and actualcostUSD.136191594 in PR repositorydocs/artifacts. Keep task open; codeCIpass doesnotprove modelaccuracy.
