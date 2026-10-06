---
type: is
id: is-01m3zaf8w0p6pzgwx6b4ztxxt5
title: "Remove the first brief's code: demo, score, compare and documents routes, the LobbyPlag demo service, make submit, the rehearsal scripts and backend/validation/"
kind: chore
status: closed
priority: 2
version: 5
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T22:06:34.367Z
updated_at: 2026-10-06T14:29:28.872Z
started_at: 2026-10-06T13:43:29.468Z
closed_at: 2026-10-06T14:29:28.872Z
close_reason: "PR #90 merged by the owner 2026-10-06: first brief's routes, DemoService, influence submit, rehearsal scripts, backend/validation/ and the frontend /workspace removed; API serves /health and the Atlas and lineage views only. All ten CI checks green (1,495 backend tests at 100% coverage, 181 frontend tests, containers job 53 s)."
resolution: null
duplicate_of: null
---
Outside the Atlas pipeline (removal of the first brief's surfaces). The Atlas brief replaced the first brief on 3 October 2026; the first brief's HTTP routes (/api/v1/amendments, /organizations, /score, /compare, /documents/extract), the LobbyPlag DemoService the API boots (503 without data/lobbyplag), the influence submit command with its schemas and service, tests/rehearse_*.py and backend/validation/ serve nothing the Atlas uses. Kept because parts 1, 4 and the practice loop import them: services/scoring.py and schemas/scoring.py (part 4's first signal), services/comparison.py and schemas/comparison.py (practice harness), services/documents.py and schemas/documents.py (part 1 attachments), repositories/lobbyplag.py's label loaders (practice loop). The frontend /workspace page and its compare-texts and document-input components call only the removed routes, so they go too. Supersedes the narrower route removal approved 2026-10-03.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/90 opened 2026-10-06. Deleted: routers demo/scoring/comparison/documents, services demo/submission, schemas demo/submission, dependencies.py, 6 test files + golden, backend/validation/, frontend /workspace + 4 components + lib/api.ts + 3 tests. Kept (imported by parts 1/4 and the practice loop): services scoring/comparison/documents, repositories/lobbyplag. make check: backend 1495 tests 100% coverage, frontend 181 tests + build, backend audit clean; frontend audit red on the pre-existing GHSA-68fv-2mgg-jv7q (PR #89). Merge after #89, then rebase onto main.
