---
type: is
id: is-01m48wmw8c166zbknxy3jazbsg
title: "API log level from the environment: INFLUENCE_LOG_LEVEL"
kind: feature
status: closed
priority: 2
version: 7
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-06T15:17:22.316Z
updated_at: 2026-10-07T08:02:05.916Z
started_at: 2026-10-06T15:20:34.426Z
closed_at: 2026-10-07T08:02:05.911Z
close_reason: "PR #94 merged by the owner 2026-10-07: INFLUENCE_LOG_LEVEL controls the influence and uvicorn loggers and fails fast on a bad value; ten checks green."
resolution: null
duplicate_of: null
---
Part 8 Publish, the view API. A host needs one setting that controls how much the API logs. Today create_app in backend/src/influence/api.py configures no logging: uvicorn sets its own loggers at its default level before importing the app, and any application logger has no handler, so its records fall to the last-resort handler at WARNING. This adds INFLUENCE_LOG_LEVEL, default info, accepting debug, info, warning, error and critical in any case, read once at startup by a new backend/src/influence/logging_setup.py that configures the root handler with a one-line format naming the logger and sets the uvicorn loggers to the same level. A wrong value stops startup with a message naming the variable and the accepted values, never a silent fallback. The Dockerfile documents the variable beside INFLUENCE_DATA_ROOT and its CMD passes the same level to uvicorn; compose.yaml passes it through from the host. Routes stay thin adapters; only how the app is assembled and run changes.

## Notes

Reopened 2026-10-07: PR #94 is still open (the owner's 'merged 94' referred to #97, the dead-code removal). Main merged into the branch after #93 and #97.
