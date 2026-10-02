---
type: is
id: is-01m3yyx3gvd489y63rvhq1zgm3
title: "R11: Deliver and rehearse the complete 60-pair and 20-proposal submission path"
kind: task
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
created_at: 2026-10-02T18:44:24.730Z
updated_at: 2026-10-02T18:44:24.730Z
---
High readiness gap. backend/src/influence/api.py:28-35 only exposes health and frontend/app/page.tsx is a landing page. The prototype main only prints evaluation metrics. No tracked inference CLI, model artifact, pair/proposal input contract, complete CSV validator or timed end-to-end rehearsal is present. Existing rev-pjk2 tracks loading, but the scorer/exporter/rehearsal need delivery tasks. Build a vertical slice producing both CSVs with exact IDs/counts, finite scores in [0,1], cached public inputs, bounded retries and atomic output. Green foundation CI and 100% coverage of 13 backend statements do not establish challenge readiness.
