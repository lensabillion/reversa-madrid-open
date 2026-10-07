---
type: is
id: is-01m4b5ar4ejj280kdbnpt9cs8p
title: Carry complete amendment quotations and source URLs into lineage evidence
kind: bug
status: in_progress
priority: 1
version: 5
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
hold: null
hold_until: null
created_at: 2026-10-07T12:27:36.462Z
updated_at: 2026-10-07T15:56:51.918Z
started_at: 2026-10-07T14:25:37.245Z
---
Parts1,5,6,8. Lineage view drops amendment text and source URLs; evidence middle column shows IDs/authors/counts only and caps carriers at6. Extend claim evidence with exact submission, amendment-change and final spans plus original source references. Browser/API contract should verify all3 quotes and clickable sources, expandable carriers and exact offset slices.

## Notes

PR #108 final head 0b58dd6: all 10 CI checks SUCCESS, CLEAN and MERGEABLE against #106. Backend 697 tests with 100% coverage; focused frontend 112 tests plus lint/types and CI production build pass. Independent Astra approved exact source identity, all-carrier access, stable quotation keys, chronology-preserving display rows and distinct-document headings. Browser DMA proof passed with no application errors. User data unchanged, website kept running. Awaiting merge; do not close yet.
