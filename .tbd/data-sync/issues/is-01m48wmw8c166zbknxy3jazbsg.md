---
type: is
id: is-01m48wmw8c166zbknxy3jazbsg
title: "API log level from the environment: INFLUENCE_LOG_LEVEL"
kind: feature
status: in_progress
priority: 2
version: 4
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-06T15:17:22.316Z
updated_at: 2026-10-06T15:45:00.634Z
started_at: 2026-10-06T15:20:34.426Z
---
Part 8 Publish, the view API. A host needs one setting that controls how much the API logs. Today create_app in backend/src/influence/api.py configures no logging: uvicorn sets its own loggers at its default level before importing the app, and any application logger has no handler, so its records fall to the last-resort handler at WARNING. This adds INFLUENCE_LOG_LEVEL, default info, accepting debug, info, warning, error and critical in any case, read once at startup by a new backend/src/influence/logging_setup.py that configures the root handler with a one-line format naming the logger and sets the uvicorn loggers to the same level. A wrong value stops startup with a message naming the variable and the accepted values, never a silent fallback. The Dockerfile documents the variable beside INFLUENCE_DATA_ROOT and its CMD passes the same level to uvicorn; compose.yaml passes it through from the host. Routes stay thin adapters; only how the app is assembled and run changes.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/94 (commit a3afa70). CI: 9 of 10 checks pass; 'Frontend dependencies have no known vulnerabilities' fails on GHSA-wq5f-xc86-pv6w in sharp 0.35.4, which also fails on main and is handled by a separate exception PR (unrelated, no frontend file touched). make check-backend: 1508 passed, coverage 100.00%, basedpyright 0 errors. Container proof: INFLUENCE_LOG_LEVEL=bogus via compose exits 1 with LogLevelError naming the variable; debug sets influence and uvicorn loggers to DEBUG and an influence.* debug record prints; warning suppresses uvicorn INFO lines. Not merged.
