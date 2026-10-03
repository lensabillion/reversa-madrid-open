---
type: is
id: is-01m40m9vqf9reh1rfw8gnrqby7
title: "Atlas shared contracts: schemas/atlas.py and fixtures under backend/tests/fixtures/atlas/"
kind: task
status: open
priority: 0
version: 1
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-03T10:17:37.262Z
updated_at: 2026-10-03T10:17:37.262Z
---
Agent 1 first handoff (docs/agents/agent-1-data-and-integration.md). Freeze the minimal LawRecord, SourceDocument, SourceSpan, Actor, Passage, Ask, Amendment, Candidate, LinkAssessment, ArticleVersion, PublicPosition, Outcome, Forecast, GraphSnapshot and RunManifest contracts with schema version, canonical IDs, code-point offsets, null/unknown states and coverage counts. Fixtures: supported copy, opposite request, short shall/may edit, ambiguous actor, missing date, missing final act, partial outcome. Fixtures enable parallel consumer work; they are not accuracy evidence. Branch feat/atlas-contracts.
