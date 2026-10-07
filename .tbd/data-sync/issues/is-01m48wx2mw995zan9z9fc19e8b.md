---
type: is
id: is-01m48wx2mw995zan9z9fc19e8b
title: Gzip the API responses
kind: feature
status: closed
priority: 2
version: 6
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies:
  - type: blocks
    target: is-01m48yd5cv7ejd873s5fyy8wge
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-06T15:21:51.003Z
updated_at: 2026-10-07T07:58:38.906Z
started_at: 2026-10-06T15:21:54.267Z
closed_at: 2026-10-07T07:58:38.902Z
close_reason: "PR #95 merged by the owner 2026-10-07: GZipMiddleware at 1 KB minimum; the AI Act view goes from 1.26 MB to 159 KB; ten checks green."
resolution: null
duplicate_of: null
---
Part 8 · Publish (the view API). Measured on 2026-10-06: GET /api/v1/lineage/2021-0106-COD answers 1,266,491 bytes with no Content-Encoding even when the client sends Accept-Encoding: gzip, so a public host sends the AI Act's 1.27 MB lineage view uncompressed on every page load. Add Starlette's GZipMiddleware (already installed with FastAPI; no new dependency) as the outermost layer in create_app() with a justified minimum_size, so responses above that size are gzip-compressed when the client accepts it while /health, the short list route, 304s and error bodies stay uncompressed. Transport only: no route or service changes. Tests prove the encoding on a real lineage.json (decompressed body equals the plain answer, ratio bound, /health never compressed); README HTTP Contract documents it; measured directly against uvicorn and through the explorer's Next.js proxy.

## Notes

PR #95 https://github.com/lensabillion/reversa-madrid-open/pull/95 (feat/api-gzip, 9573947). CI: 9 of 10 checks pass, including Backend tests pass with full coverage (2m35s) and Containers build and serve. The one failure, Frontend dependencies have no known vulnerabilities, is GHSA-wq5f-xc86-pv6w in sharp 0.35.4, which fails on main's own lockfile and is handled by a separate exception PR; this PR does not touch frontend/. make check-backend locally: 1499 passed, coverage 100%. Measured: AI Act view 1,262,923 -> 158,677 bytes with gzip, directly and through the Next.js dev proxy (relayed unchanged); /health plain. Awaiting review; close on merge.
