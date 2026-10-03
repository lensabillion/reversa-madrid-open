---
type: is
id: is-01m3yyx33b3kpjfnq5h8mvjzsp
title: "R9: Make Challenge 03 experimental evidence reproducible from a fresh checkout"
kind: task
status: open
priority: 0
version: 3
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
created_at: 2026-10-02T18:44:24.298Z
updated_at: 2026-10-03T08:53:14.817Z
---
High. .gitignore excludes attic and data, and facts.yaml:152/161/171/181 points at nonexistent influence/evaluate.py and influence/corpus.py. No persisted model/metrics/prediction artifact exists in the prototype tree; embedding cache keys omit model revision and encoding configuration. Current rerun used cached embeddings, not a fresh download. Commit a supported benchmark runner, pinned model revision, data-fetch manifest, fold IDs, seeds and machine-readable results; keep large public data gitignored.

## Notes

2026-10-03, Atlas re-plan (rev-sz6q): now a scored criterion: the report criterion opens the repo and checks 'anyone can rerun it'. Pinned downloads, model revisions, seeds and a one-command rebuild.
