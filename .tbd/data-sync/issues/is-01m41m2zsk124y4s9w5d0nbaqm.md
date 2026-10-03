---
type: is
id: is-01m41m2zsk124y4s9w5d0nbaqm
title: Add the DSA, DMA and Data Act lineage snapshots to mock-data/
kind: chore
status: in_progress
priority: 2
version: 3
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-03T19:33:06.483Z
updated_at: 2026-10-03T22:38:18.097Z
started_at: 2026-10-03T19:33:10.966Z
---
Copy the lineage.json of the Digital Services Act (2020/0361(COD)), Digital Markets Act (2020/0374(COD)) and Data Act (2022/0047(COD)) runs into mock-data/laws/<slug>/, with a provenance row each in mock-data/README.md, so someone who clones the repository can open those laws' lineage views without running the pipeline or holding a TypeSafe key for Jev. data/ stays ignored (AGENTS.md: downloads are never committed; 1.7 GB with two files over GitHub's 100 MB limit). The runs were made with backend source src-e6c32911fa16, identical to main at d7de70d. Part: publish (explorer).

## Notes

PR: https://github.com/lensabillion/reversa-madrid-open/pull/86 (branch chore/mock-data-dsa-dma-data-act, commit 8aa955c). Verified: byte-identical copies; main's API lists and serves all five laws from mock-data; /lineage renders each new law with no console errors.
