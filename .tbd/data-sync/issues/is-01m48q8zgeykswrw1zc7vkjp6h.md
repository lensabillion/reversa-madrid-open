---
type: is
id: is-01m48q8zgeykswrw1zc7vkjp6h
title: "Containers: one command builds and runs the API and the frontend"
kind: task
status: in_progress
priority: 1
version: 2
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-06T13:43:29.549Z
updated_at: 2026-10-06T13:44:30.306Z
started_at: 2026-10-06T13:44:30.303Z
---
Part 8 · Publish (the open repository anyone can rerun). Add backend/Dockerfile (Python 3.14.7 slim, uv 0.12.8, uv sync --locked --no-dev, non-root, /health check, INFLUENCE_DATA_ROOT=/data), frontend/Dockerfile (Node 24.15.0, npm ci under frontend/.npmrc, next build, next start) and a root compose.yaml wiring them with INFLUENCE_API_URL and a bind mount of ./data; a make up target; a CI job that builds both images and curls the health route. Base images pinned by digest (SUPPLY-CHAIN-SECURITY.md rule 4 applied to images).
