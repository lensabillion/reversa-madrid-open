---
type: is
id: is-01m3z1ex69d9rs01yhh46s2zcc
title: Build a polished interactive evidence frontend for the GDPR demo
kind: feature
status: in_progress
priority: 1
version: 7
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
child_order_hints:
  - is-01m3z2nr2scf757wh9128w9t6s
hold: null
hold_until: null
created_at: 2026-10-02T19:29:05.224Z
updated_at: 2026-10-02T20:20:54.505Z
started_at: 2026-10-02T19:29:47.462Z
---
Build the user-requested creative, high-standard frontend on the typed evidence API: searchable amendments, original and changed text with evidence, sources and provenance, interactive influence graph, organizations and explicit loading/error/limited-score states. Accessible and responsive. Keep historical labels distinct from computed similarity. Deliver documented PR with full checks and CI.

## Notes

Frontend PR #12: https://github.com/lensabillion/reversa-madrid-open/pull/12. All nine CI checks passed. Backend #10 and #11 merged. Combined make check: 106 backend tests with full branch coverage, 33 frontend tests, production build and clean audits. Live browser verified real PDF upload/page review/comparison, ITRE 616 evidence and 390-pixel network without page overflow. frontend/README.md and docs/implementation-status.md retain evaluation and handoff. PR explains every UI section and changed file. Keep open until merge.
