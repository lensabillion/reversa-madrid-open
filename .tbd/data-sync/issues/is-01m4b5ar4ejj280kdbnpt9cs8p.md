---
type: is
id: is-01m4b5ar4ejj280kdbnpt9cs8p
title: Carry complete amendment quotations and source URLs into lineage evidence
kind: bug
status: in_progress
priority: 1
version: 4
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
hold: null
hold_until: null
created_at: 2026-10-07T12:27:36.462Z
updated_at: 2026-10-07T15:55:30.091Z
started_at: 2026-10-07T14:25:37.245Z
---
Parts1,5,6,8. Lineage view drops amendment text and source URLs; evidence middle column shows IDs/authors/counts only and caps carriers at6. Extend claim evidence with exact submission, amendment-change and final spans plus original source references. Browser/API contract should verify all3 quotes and clickable sources, expandable carriers and exact offset slices.

## Notes

PR #108 published at 0b58dd6, base codex/lineage-carrier-evidence (#106 now contains merged #107). Source metadata and identity work is complete; 697 backend tests at 100% coverage and 101 frontend full-gate tests passed before browser follow-up. Browser follow-up c817d77 fixes same-start quotation keys, preserves distinct timing/eligibility rows, and counts distinct submission documents. Focused frontend suite now 112 tests, Biome and strict types pass. Independent Astra final review approved. Browser DMA shows exact source links, both overlapping quotations and 20 expandable carriers with no application errors. New-head CI pending. Four-law provenance rehearsal retained all 328 input files unchanged; no paid calls.
