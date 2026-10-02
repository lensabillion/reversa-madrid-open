---
type: is
id: is-01m3z1ex69d9rs01yhh46s2zcc
title: Build a polished interactive evidence frontend for the GDPR demo
kind: feature
status: in_progress
priority: 1
version: 4
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T19:29:05.224Z
updated_at: 2026-10-02T19:46:25.499Z
started_at: 2026-10-02T19:29:47.462Z
---
Build the user-requested creative, high-standard frontend on the typed evidence API: searchable amendments, original and changed text with evidence, sources and provenance, interactive influence graph, organizations and explicit loading/error/limited-score states. Accessible and responsive. Keep historical labels distinct from computed similarity. Deliver documented PR with full checks and CI.

## Notes

Frontend implementation complete on feat/evidence-workspace. User light analytical design and strict subtraction applied: slogan/ornament removed, no new dependencies.24frontendtests pass incl stale response, source switching, Unicode offset and graph hitbox regression; full makecheck green, production build verified. Browser QA found/fixed overlapping graph buttons and narrow fieldset overflow. Production preview running localhost3000, backend8000, real public dataset. Separate first-principles frontend PR pending final browser verification; depends on backend PR10/rev-ic1h. Both beads stay open until merge.
