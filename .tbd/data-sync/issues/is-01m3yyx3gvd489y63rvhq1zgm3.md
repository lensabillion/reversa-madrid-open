---
type: is
id: is-01m3yyx3gvd489y63rvhq1zgm3
title: "R11: Deliver and rehearse the complete 60-pair and 20-proposal submission path"
kind: task
status: closed
priority: 1
version: 2
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
created_at: 2026-10-02T18:44:24.730Z
updated_at: 2026-10-03T08:52:04.450Z
closed_at: 2026-10-03T08:52:04.449Z
close_reason: "Superseded 2026-10-03: the organizers replaced the Challenge 03 brief; the Influence Atlas brief has no 60-pair or 20-proposal CSV deliverable. The validated pairs.csv path exists on main (PR #19). The new end-to-end path is the any-law command, tracked under rev-sz6q's children."
resolution: canceled
duplicate_of: null
---
High readiness gap. backend/src/influence/api.py:28-35 only exposes health and frontend/app/page.tsx is a landing page. The prototype main only prints evaluation metrics. No tracked inference CLI, model artifact, pair/proposal input contract, complete CSV validator or timed end-to-end rehearsal is present. Existing rev-pjk2 tracks loading, but the scorer/exporter/rehearsal need delivery tasks. Build a vertical slice producing both CSVs with exact IDs/counts, finite scores in [0,1], cached public inputs, bounded retries and atomic output. Green foundation CI and 100% coverage of 13 backend statements do not establish challenge readiness.
