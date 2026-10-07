---
type: is
id: is-01m4b7dmy0z6bhs3z3hecdxx5t
title: Retire the Atlas branch and keep the lineage website
kind: task
status: in_progress
priority: 1
version: 7
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-07T13:04:08.639Z
updated_at: 2026-10-07T13:47:53.521Z
started_at: 2026-10-07T13:06:37.535Z
---
Final owner decision 7 October 2026 after viewing the temporary Saved analysis preview: remove it, the whole line on atlas.json. Remove the uncommitted analysis page/API and the Atlas producer plus offline-only forecast/report/audit/directions/channels/coordinated/batch/practice/model experiment code. Keep the lineage website, health/lineage API, setup/collect/lineage CLI including optional Jev, source/provenance/cache helpers, persisted collection/lineage compatibility, build/test/quality tooling. Preserve every document, evaluation evidence and ignored user data. Parts 1-8 scope reduction authorized; Astra judges boundaries and reviews, Sol handles mechanics. No analytic accuracy fixes claimed. Verify identical fixed-input lineage/Jev behavior, no unreachable obsolete runtime imports, full make check, populated website browser pass and CI.

## Notes

Final verification: PR102 head97c52922222bde32c37024dc71cfa2757a411909 has all10 CI checks SUCCESS, including container startup/proxy probes, backend100%coverage and both dependency audits. GitHub CLEAN/MERGEABLE; left open and unmerged. Responsive SVG architecture visually verified in browser; README updated. Clarification: backend/src/influence/services/lineage_jev.py and its tests are RETAINED; only backend/benchmarks/lineage_jev.py (separate runner) is deleted, measurements documented. No data edits, paid calls or accuracy fixes. Local ports3041,8041 serve website/API;8042 serves architecture artwork. Prior PR100 all10checks green but behindmain,PR101 all10green clean; no reviews/comments.
