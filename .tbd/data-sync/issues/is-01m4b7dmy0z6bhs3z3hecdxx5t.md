---
type: is
id: is-01m4b7dmy0z6bhs3z3hecdxx5t
title: Retire the Atlas branch and keep the lineage website
kind: task
status: in_progress
priority: 1
version: 6
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-07T13:04:08.639Z
updated_at: 2026-10-07T13:42:37.826Z
started_at: 2026-10-07T13:06:37.535Z
---
Final owner decision 7 October 2026 after viewing the temporary Saved analysis preview: remove it, the whole line on atlas.json. Remove the uncommitted analysis page/API and the Atlas producer plus offline-only forecast/report/audit/directions/channels/coordinated/batch/practice/model experiment code. Keep the lineage website, health/lineage API, setup/collect/lineage CLI including optional Jev, source/provenance/cache helpers, persisted collection/lineage compatibility, build/test/quality tooling. Preserve every document, evaluation evidence and ignored user data. Parts 1-8 scope reduction authorized; Astra judges boundaries and reviews, Sol handles mechanics. No analytic accuracy fixes claimed. Verify identical fixed-input lineage/Jev behavior, no unreachable obsolete runtime imports, full make check, populated website browser pass and CI.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/102 opened from codex/website-only at da5ca727ad412ce73ca6db4aa9ed631073fb014c, based on codex/repository-consistency-review. Removes retired Atlas/offline branch and includes README SVG architecture. make check passed: 640 backend tests; 100% line/branch coverage (3838 statements,1028 branches);59 frontend tests; build/types/lint/catalogs/audits pass. Populated browser list/summary/graph/evidence verified, site running at 127.0.0.1:3041. Fixed-input mocked Jev snapshot byte-identical to015bdac. Prior PR100/101 checked: each10 checks green, no reviews/comments;100 mergeable but behindmain,101 clean. NewPR CI pending. Bead remains in_progress until merge.
