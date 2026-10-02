---
type: is
id: is-01m3z0te5ze4n2qcvsy0b0q6e8
title: Build the GDPR evidence-demo backend with typed API and separated domain services
kind: feature
status: in_progress
priority: 1
version: 6
delegate: codex@lensas-macbook-air.local
labels: []
dependencies:
  - type: blocks
    target: is-01m3z1ex69d9rs01yhh46s2zcc
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T19:17:54.489Z
updated_at: 2026-10-02T19:46:25.328Z
started_at: 2026-10-02T19:18:44.595Z
---
Implement the starting demo backend from the agreed new architecture: local public LobbyPlag ingestion, amendment/source evidence, organization-MEP graph, transparent automated baseline scoring, separated schemas/routers/business logic, documented API and reproducible validation. Keep historical verification labels separate from model scores. Assess ML necessity without claiming trained predictive quality unsupported by labels. Deliver a first-principles PR with full gates and CI.

## Notes

PR10 https://github.com/lensabillion/reversa-madrid-open/pull/10 is ready for review: all9GitHubchecks green on7593653. Backend74tests100%line/branch345statements. Full local makecheck green and independent review complete. First-principles PR documents all files, alternatives, real data measurements, ML limitations. Leave open until PR merges.
