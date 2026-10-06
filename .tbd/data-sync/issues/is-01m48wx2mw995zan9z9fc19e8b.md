---
type: is
id: is-01m48wx2mw995zan9z9fc19e8b
title: Gzip the API responses
kind: feature
status: in_progress
priority: 2
version: 2
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-06T15:21:51.003Z
updated_at: 2026-10-06T15:21:54.267Z
started_at: 2026-10-06T15:21:54.267Z
---
Part 8 · Publish (the view API). Measured on 2026-10-06: GET /api/v1/lineage/2021-0106-COD answers 1,266,491 bytes with no Content-Encoding even when the client sends Accept-Encoding: gzip, so a public host sends the AI Act's 1.27 MB lineage view uncompressed on every page load. Add Starlette's GZipMiddleware (already installed with FastAPI; no new dependency) as the outermost layer in create_app() with a justified minimum_size, so responses above that size are gzip-compressed when the client accepts it while /health, the short list route, 304s and error bodies stay uncompressed. Transport only: no route or service changes. Tests prove the encoding on a real lineage.json (decompressed body equals the plain answer, ratio bound, /health never compressed); README HTTP Contract documents it; measured directly against uvicorn and through the explorer's Next.js proxy.
