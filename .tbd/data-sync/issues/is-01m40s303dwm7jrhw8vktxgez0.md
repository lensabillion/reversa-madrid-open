---
type: is
id: is-01m40s303dwm7jrhw8vktxgez0
title: Complete consolidated-plan signal calculation and evaluation
kind: task
status: in_progress
priority: 0
version: 4
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-03T11:41:15.245Z
updated_at: 2026-10-03T13:02:52.732Z
started_at: 2026-10-03T11:41:31.110Z
---
User explicitly requests complete calculation per docs/plan.md, no omitted signals. Extend Agent2 assessment/outcome branches rather than duplicate them. Scope: requirement coverage matrix, measured semantic retrieval, rarity/alignment/background/mutual/legal signals, fitted grouped combiner and threshold evidence, integration/handoff. No unapproved external judge/API spending; no probability/publication claims without evaluation.

## Notes

PR #48 https://github.com/lensabillion/reversa-madrid-open/pull/48 implements and evaluates fitted signals/local models; all9CI pass at9c15f42, main2fbb229 integrated. Local gate941backend100%branch/94frontend. No model promoted: baseline P20=.9801 vs deterministic/background=.9765,Qwen+NLI=.9671,E5+NLI=.9718. Real Gate3 audit completed with3subagents: after crash fix PR52, cached build249.318s yields only2published links (same AI HLEG definition/amendment), below20;10randomread unavailable. All checked spans exact but origin interpretation weak. Runtime may/shall adversarial case still publishes(.7843), rev-sbrp. Prose-aware scoring/calibration remains with part4 owner rev-nuk5/rev-zzur; no duplicate scorer started. Full CLI initially failed459.815s; only cached service rebuild succeeds. Gate3 remains open; Gate7 independent40link/twohuman audit is separate and not claimed. Reproducible results/status in PR52 docs/implementation-status.md and ignored data/laws/2021-0106-COD audit artifacts.
