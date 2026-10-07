---
type: is
id: is-01m4b7dmy0z6bhs3z3hecdxx5t
title: Keep only code supporting the lineage website and its data generation
kind: task
status: in_progress
priority: 1
version: 2
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-07T13:04:08.639Z
updated_at: 2026-10-07T13:06:37.535Z
started_at: 2026-10-07T13:06:37.535Z
---
Owner decision 7 October 2026: remove tracked code and commands whose removal does not affect the current website, preserving documents. Retain frontend, lineage API, setup/collect/lineage including optional Jev, shared data/source helpers, and required build/test/quality tooling. Retire ask-first Atlas and all offline-only features, experiments and tests specific to them. Preserve ignored user data and documentary/evaluation evidence. Parts 1,2,3,4,5,6,8; this explicitly supersedes retaining offline Atlas consumers. Astra supplies architecture judgment; Sol handles mechanical implementation. Verify identical retained behavior, strict full gate and populated website.
