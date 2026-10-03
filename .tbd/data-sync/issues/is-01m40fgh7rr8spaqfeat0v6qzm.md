---
type: is
id: is-01m40fgh7rr8spaqfeat0v6qzm
title: "Part 3 · Coordinated amendments: near-identical amendments tabled by MEPs of different groups, a sign of a shared outside draft"
kind: feature
status: in_progress
priority: 1
version: 4
delegate: claude-code@omni
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T08:53:53.016Z
updated_at: 2026-10-03T13:23:46.228Z
started_at: 2026-10-03T13:12:29.082Z
---
Cheap first insight from data already on disk: cluster near-identical amendment changes within a procedure (MinHash or exact normalized text) and flag clusters spanning political groups. Not proof of lobbying by itself; becomes a candidate whose source part 3/4 then looks for in the law's submissions. Measured from Parltrack ep_amendments only.

## Notes

2026-10-03 16:05 CEST: branch feat/coordinated-amendments pushed (4d40aaf). services/coordinated.py + influence coordinated <law> + make coordinated. Backend gate: 999 tests, 100% branch coverage. Measured (WSL2, Core Ultra 7 258V, --no-attachments, HTTP cached): AI Act 83 of 269 clusters span groups, DSA 80 of 508, Data Act 72 of 173; about 4 s after collect. PR follows.
