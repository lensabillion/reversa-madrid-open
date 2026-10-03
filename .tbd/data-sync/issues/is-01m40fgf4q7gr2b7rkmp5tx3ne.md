---
type: is
id: is-01m40fgf4q7gr2b7rkmp5tx3ne
title: "Part 2 · Resolve actors: one identity per organization and MEP across consultations, register, meetings and amendments"
kind: feature
status: open
priority: 1
version: 2
labels: []
dependencies:
  - type: blocks
    target: is-01m40fgfhe8qaj6srfqh1r6ada
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-03T08:53:50.870Z
updated_at: 2026-10-03T08:54:03.003Z
---
Atlas part 2 (explainer §6). Key on the Transparency Register ID where a source carries it (HYS OPC CSV, Commission meetings OrgId, Integrity Watch TR-match file), else normalized names (legal-form suffixes, case, accents) with rapidfuzz, keeping every alias with its source. MEPs keyed by EP id (Parltrack meps, Integrity Watch epid). Output: actor table + alias table. Measure: precision of merges on a random sample; never merge across different register IDs.
