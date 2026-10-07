---
type: is
id: is-01m4b5at47s7y16cs87cdyka65
title: Use adopted-only document counts in the lineage summary funnel
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
created_at: 2026-10-07T12:27:38.502Z
updated_at: 2026-10-07T14:26:58.424Z
started_at: 2026-10-07T14:08:52.192Z
---
Parts7-8. lineageFunnel uses documents_with_origin across adopted and tabled-only origins under adopted-wording narrative. Reproduced snapshots: AI Act203 displayed vs79 eligible adopted documents out of788; DGA54 vs18 out of1461. Keep tabled-only and adopted metrics distinct; test one adopted and two tabled-only documents.

## Notes

PR #103 https://github.com/lensabillion/reversa-madrid-open/pull/103; ef34c94; all 10 CI checks pass including backend full coverage, frontend gates/build/audits and containers. Local frontend gate: 66 tests/7 files. Independent Astra review approved actual diff. Open pending merge; no claim of analytical validation.
