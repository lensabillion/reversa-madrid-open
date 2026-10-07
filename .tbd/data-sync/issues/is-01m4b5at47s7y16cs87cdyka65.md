---
type: is
id: is-01m4b5at47s7y16cs87cdyka65
title: Use adopted-only document counts in the lineage summary funnel
kind: bug
status: in_progress
priority: 1
version: 3
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
hold: null
hold_until: null
created_at: 2026-10-07T12:27:38.502Z
updated_at: 2026-10-07T14:25:59.493Z
started_at: 2026-10-07T14:08:52.192Z
---
Parts7-8. lineageFunnel uses documents_with_origin across adopted and tabled-only origins under adopted-wording narrative. Reproduced snapshots: AI Act203 displayed vs79 eligible adopted documents out of788; DGA54 vs18 out of1461. Keep tabled-only and adopted metrics distinct; test one adopted and two tabled-only documents.

## Notes

PR #103 https://github.com/lensabillion/reversa-madrid-open/pull/103; head ef34c94; based on updated #100. Full frontend gate passes: 66 tests/7 files, Biome, strict types, build. Astra independently approved actual diff; no blockers. CI pending. Fixes adopted-only document arithmetic; does not validate evidence.
