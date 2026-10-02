---
type: is
id: is-01m3z1ex69d9rs01yhh46s2zcc
title: Build a polished interactive evidence frontend for the GDPR demo
kind: feature
status: in_progress
priority: 1
version: 6
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
child_order_hints:
  - is-01m3z2nr2scf757wh9128w9t6s
hold: null
hold_until: null
created_at: 2026-10-02T19:29:05.224Z
updated_at: 2026-10-02T20:15:50.923Z
started_at: 2026-10-02T19:29:47.462Z
---
Build the user-requested creative, high-standard frontend on the typed evidence API: searchable amendments, original and changed text with evidence, sources and provenance, interactive influence graph, organizations and explicit loading/error/limited-score states. Accessible and responsive. Keep historical labels distinct from computed similarity. Deliver documented PR with full checks and CI.

## Notes

Light evidence workspace and Compare texts implemented on feat/evidence-workspace, stacked on ingestion PR #11. Final combined make check passed: 106 backend tests with 100% branch coverage, 33 frontend tests, production build and clean audits. Independent review fixed deletion-only result view and non-JSON upload error messages with regressions. Browser verification and first-principles frontend PR publication in progress. No trained influence model or full competition CSV runner claimed.
