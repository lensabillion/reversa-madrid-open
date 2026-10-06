---
type: is
id: is-01m48q8zgeykswrw1zc7vkjp6h
title: "Containers: one command builds and runs the API and the frontend"
kind: task
status: in_progress
priority: 1
version: 3
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-06T13:43:29.549Z
updated_at: 2026-10-06T13:53:08.951Z
started_at: 2026-10-06T13:44:30.303Z
---
Part 8 · Publish (the open repository anyone can rerun). Add backend/Dockerfile (Python 3.14.7 slim, uv 0.12.8, uv sync --locked --no-dev, non-root, /health check, INFLUENCE_DATA_ROOT=/data), frontend/Dockerfile (Node 24.15.0, npm ci under frontend/.npmrc, next build, next start) and a root compose.yaml wiring them with INFLUENCE_API_URL and a bind mount of ./data; a make up target; a CI job that builds both images and curls the health route. Base images pinned by digest (SUPPLY-CHAIN-SECURITY.md rule 4 applied to images).

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/88 opened 2026-10-06. Verified locally (Apple M5, Docker 29.4.2 arm64): compose build 17 s, make check-containers 12.9 s against data/, mock-data/ and an empty dir; browser check of /lineage from the containers with both API calls proxied 200. Images: backend 336 MB, frontend 410 MB. Not verified: the amd64 CI run (first run on the PR). After merge: add the 'Containers build and serve the API and the explorer' context to the main branch protection (rev-xpux).
