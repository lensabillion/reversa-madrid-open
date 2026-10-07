---
type: is
id: is-01m4b5agdap7dwsvf1z7697rq6
title: Enforce a shared publication policy for lineage graph and rankings
kind: bug
status: open
priority: 1
version: 2
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
created_at: 2026-10-07T12:27:28.553Z
updated_at: 2026-10-07T14:10:49.522Z
---
Parts 4, 6, 7, 8 and practice loop. Architecture requires audited published-only claims; lineage has chronology/citation eligibility but no publication status or bound audit. Add an explicit claim/publication policy shared by graph, rankings, report and sample. Preserve unreviewed associations as explicitly experimental. Evidence: schemas/lineage.py OriginMatch, lineage_assembly.py, frontend/lib/lineage-graph.ts. Validate unaudited claims cannot enter defended rankings. Audit 2026-10-07 at efea068; related rev-ffsz and rev-9nz9.

## Notes

Owner chose 7October2026: Show clearly labeled experimental associations, rather than hide unaudited links. Implement explicit exploratory status and remove defended causal/validated ranking claims consistently. This is not a precision audit. Keep exact evidence/correct joins, eligibility and unknowns; no fabricated verification or thresholds.
