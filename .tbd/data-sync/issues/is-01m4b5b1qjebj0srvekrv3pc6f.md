---
type: is
id: is-01m4b5b1qjebj0srvekrv3pc6f
title: Define shared analysis metrics for explorer and offline report
kind: bug
status: open
priority: 2
version: 1
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
created_at: 2026-10-07T12:27:46.289Z
updated_at: 2026-10-07T12:27:46.289Z
---
Parts6-8. frontend README says frontend ranks nothing, but rankOrganisations computes eligibility, phrase aggregation and ranking. Offline report uses Atlas full-win rates while UI uses lineage phrase counts. Define metric IDs/populations/denominators/order and publication contract in backend outputs or explicitly specify derivation parity. Verify same metric agrees between UI/report; do not equate phrase survival to distinct legal wins.
