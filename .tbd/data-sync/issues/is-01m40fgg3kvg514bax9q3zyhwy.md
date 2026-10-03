---
type: is
id: is-01m40fgg3kvg514bax9q3zyhwy
title: "Part 7 · Rank: who actually wins, by actor, actor type, topic and year, compared with lobby spend"
kind: feature
status: in_progress
priority: 1
version: 4
delegate: codex@lensas-macbook-air.local
labels: []
dependencies:
  - type: blocks
    target: is-01m40fggfj56f94fph17m88zna
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T08:53:51.858Z
updated_at: 2026-10-03T11:06:39.747Z
started_at: 2026-10-03T10:38:24.725Z
---
Atlas part 7. Heard / adopted by Parliament / won rates per actor from part 5 over part 6; topics from OEIL subject codes; spend and category from the Transparency Register; 'wins above what spend predicts' as the headline. Every ranking row links to its edges. Small-number caution: show counts beside rates.

## Notes

Agent 3 descriptive outcome consumer implemented in services/atlas_analysis.py against merged atlas-1. PR https://github.com/lensabillion/reversa-madrid-open/pull/28 at cac0f29, all 9 CI checks passed. Consumes every supplied canonical request including unmatched, counts each once per stage, retains supporting outcome/evidence IDs, unknowns, coalition attribution, observed coverage and known inventory mismatches. Raw rate ordering with explicit counts; topic exact subject and year procedure-reference filters. Fixture final totals full2/partial1/not_observed2/unknown1, assessed5, rate0.4; synthetic behavior evidence, no causal claim. make check passed 274 backend tests and 100% branch coverage, 37 frontend tests/build, catalogs/audits clean. 1000 cached tiny-fixture graph+aggregation runs 0.1097s on Apple M5 Python3.14.7; excludes live pipeline. Semantic ask dedup, real outcome quality, spend comparisons and causal estimates remain outside this slice; bead stays open pending merge/integration.
