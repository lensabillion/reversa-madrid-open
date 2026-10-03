---
type: is
id: is-01m40fgf4q7gr2b7rkmp5tx3ne
title: "Part 2 · Resolve actors: one identity per organization and MEP across consultations, register, meetings and amendments"
kind: feature
status: open
priority: 1
version: 3
labels: []
dependencies:
  - type: blocks
    target: is-01m40fgfhe8qaj6srfqh1r6ada
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-03T08:53:50.870Z
updated_at: 2026-10-03T11:23:05.163Z
---
Atlas part 2 (explainer §6). Key on the Transparency Register ID where a source carries it (HYS OPC CSV, Commission meetings OrgId, Integrity Watch TR-match file), else normalized names (legal-form suffixes, case, accents) with rapidfuzz, keeping every alias with its source. MEPs keyed by EP id (Parltrack meps, Integrity Watch epid). Output: actor table + alias table. Measure: precision of merges on a random sample; never merge across different register IDs.

## Notes

2026-10-03 13:25 CEST, state of main at bdb0c61 (recorded by cloud session claude/eloquent-allen-jbxbmy): Actor resolution landed in PR #26: repositories/register.py (17,897 entries, export of 2 Oct; XML 1.1 control characters handled line by line) and services/actors.py; 45 tests, 100% branch coverage (measured by Agent 1). Reported on real data: all 304 AI Act submissions resolve in 0.12 s: 173 by register ID, 30 exact name, 4 acronym and 6 fuzzy proposals, 79 unresolved, 12 citizens aggregated; 25 cite register IDs absent from today's export. Open: owner to confirm the Europe/European/EU exact-name rule; the citizens aggregate uses resolution=unresolved (an `aggregate` value needs a schema bump). Not yet run inside a collect run. Unclaimed.
