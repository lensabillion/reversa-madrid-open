---
type: is
id: is-01m4b7dmy0z6bhs3z3hecdxx5t
title: Retire the Atlas branch and keep the lineage website
kind: task
status: closed
priority: 1
version: 11
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-07T13:04:08.639Z
updated_at: 2026-10-07T14:08:52.368Z
started_at: 2026-10-07T13:06:37.535Z
closed_at: 2026-10-07T14:08:52.368Z
close_reason: PR101 and PR102 are merged into the parent branding branch (PR100), verified on GitHub 7 October2026. Their audit/cleanup deliverables and final CI passed; release to main remains under PR100/rev-3n26. New analytical fixes are separate beads.
resolution: null
duplicate_of: null
---
Final owner decision 7 October 2026 after viewing the temporary Saved analysis preview: remove it, the whole line on atlas.json. Remove the uncommitted analysis page/API and the Atlas producer plus offline-only forecast/report/audit/directions/channels/coordinated/batch/practice/model experiment code. Keep the lineage website, health/lineage API, setup/collect/lineage CLI including optional Jev, source/provenance/cache helpers, persisted collection/lineage compatibility, build/test/quality tooling. Preserve every document, evaluation evidence and ignored user data. Parts 1-8 scope reduction authorized; Astra judges boundaries and reviews, Sol handles mechanics. No analytic accuracy fixes claimed. Verify identical fixed-input lineage/Jev behavior, no unreachable obsolete runtime imports, full make check, populated website browser pass and CI.

## Notes

FINAL correctedhead50dd222e257f82a10164f0b17b954197b816f080: all10PR102CIchecksSUCCESS includingBackend665tests/fullcoverage59s andContainers1m7s. IndependentlineageQAtoolretained, productionJevretained, realAI/DataActlexicalviewsunchanged, mockJevunchanged. PR100/101actualdiffsindependentlyreviewedwithnointroducedblockers, both10green ontheirheads;PR100behindmain. No PRmerged. WorkcompleteinPR; beadremainsin_progressuntilmerge. Knownanalyticalaccuracyfindingsremainopen—not100%correctnessclaim.
