---
type: is
id: is-01m48xg95snhrfdmss851e1wn0
title: "Remove dead code: unreferenced modules, functions, constants, schema records and their test-only coverage"
kind: chore
status: in_progress
priority: 2
version: 4
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-06T15:32:20.280Z
updated_at: 2026-10-07T07:40:15.824Z
started_at: 2026-10-06T15:32:27.694Z
---
Cross-cutting chore (parts 1, 4, 5, 7 and the practice loop; no part's behaviour changes). An AST cross-reference of every top-level definition in backend/src, backend/benchmarks, backend/models, scripts and frontend against the whole repository, plus vulture 2.14 and a module import graph, found code that nothing on a reachable path (make targets, documented python -m commands, the API, the explorer) uses: whole modules reached only by their own tests (extraction/manifest.py, extraction/tables.py, services/calculation.py), test-only functions (cellar.resolve_position_celex, cellar.procedure_for_celex, parltrack.mep_actors, register.register_export_date, calibration.precision_report, judge.best_sentence, law_query.com_reference_from_celex, outcomes.outcome_result, pipeline.list_views, ranking_signals.reciprocal_rank_fusion), the ActorIndex resolver in extraction/names.py that services/actors.py replaced, the never-read SourceSpec.target_tables, DataLayout.table/parsed/manifest, the PublicPosition record no part produces or reads, and unreferenced constants (jev_judge.PROMPT_REVISION, OWN_WORDING, qwen_onnx.MODEL_NAME, atlas_fixture.SIX_MONTHS). Each goes with its tests, fixtures and documentation. Kept because a documented command reaches them: practice/*.py, benchmarks/*.py, backend/models/, the extraction CLI.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/97 opened 2026-10-07 from chore/remove-dead-code (91f7f87, main 409ddbd merged in). Deleted 2,526 lines, added 159: extraction/manifest.py, extraction/tables.py, services/calculation.py (+ its two test files), the ActorIndex resolver, pipeline.list_views and the AtlasLaw* models, judge.best_sentence, PublicPosition, SourceSpec.target_tables, DataLayout.table/parsed/manifest, eight test-only repository/service functions and four constants; README, design notes and status updated. make check on the branch: 1369 backend tests at 100% branch coverage, 54 frontend tests, build, both audits clean. Judgement calls flagged in the PR: calculation.py and PublicPosition were designed-but-unwired work. Ten CI checks pending at open.
