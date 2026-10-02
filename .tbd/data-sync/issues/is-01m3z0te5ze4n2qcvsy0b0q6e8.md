---
type: is
id: is-01m3z0te5ze4n2qcvsy0b0q6e8
title: Build the GDPR evidence-demo backend with typed API and separated domain services
kind: feature
status: in_progress
priority: 1
version: 3
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T19:17:54.489Z
updated_at: 2026-10-02T19:29:51.006Z
started_at: 2026-10-02T19:18:44.595Z
---
Implement the starting demo backend from the agreed new architecture: local public LobbyPlag ingestion, amendment/source evidence, organization-MEP graph, transparent automated baseline scoring, separated schemas/routers/business logic, documented API and reproducible validation. Keep historical verification labels separate from model scores. Assess ML necessity without claiming trained predictive quality unsupported by labels. Deliver a first-principles PR with full gates and CI.

## Notes

Implementation in /private/tmp/reversa-demo-backend on feat/gdpr-demo-backend. Router/repository/service/schema separation and lexical baseline implemented. Full corpus integration found duplicate candidate rows; explicit coalescing and coverage fixes in progress. Hugging Face BGE/Qwen rerankers confirmed research candidates; relevance is not influence probability, pending grouped evaluation. User also authorized frontend rev-oze0 and chose light analytical design.
