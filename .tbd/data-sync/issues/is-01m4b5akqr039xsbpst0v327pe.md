---
type: is
id: is-01m4b5akqr039xsbpst0v327pe
title: Bind semantic origins to the adopted change actually supported
kind: bug
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
created_at: 2026-10-07T12:27:31.960Z
updated_at: 2026-10-07T12:27:31.960Z
---
Parts 4-6. lineage_jev.py:62 chooses phrase_ids[0]; judges whole amendment at79-80; attaches first phrase at98-100. Reproduced request about rejected lost text attached to adopted novel text using deterministic judge stub; prompt has no final text. Require exact adopted span evidence and distinguish tabled support from adoption. Test partial adoption and two adopted phrase selection.
