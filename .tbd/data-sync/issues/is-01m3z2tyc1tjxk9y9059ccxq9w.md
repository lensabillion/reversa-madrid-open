---
type: is
id: is-01m3z2tyc1tjxk9y9059ccxq9w
title: Extract PDF and text uploads into a validated page-aware document contract
kind: feature
status: closed
priority: 1
version: 4
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T19:53:08.224Z
updated_at: 2026-10-02T20:20:13.169Z
started_at: 2026-10-02T19:53:28.626Z
closed_at: 2026-10-02T20:20:13.168Z
close_reason: "PR #11 merged 2026-10-02T20:18:12Z: https://github.com/lensabillion/reversa-madrid-open/pull/11. All nine CI checks passed; 106 backend tests with 100% branch coverage and full make check. Extraction, nullable-original comparison and Markdown architecture/handoff delivered."
resolution: null
duplicate_of: null
---
Shared ingestion service and thin HTTP adapter for public PDF/text inputs. Preserve page numbers and extracted text, bound input bytes/pages/output, reject corrupt/encrypted/unsupported files explicitly, identify scanned pages without inventing OCR, support frontend extraction review and future batch reuse. Pin pypdf under supply-chain policy, tests/full gates/first-principles PR. Separate from semantic scoring/adoption.

## Notes

Backend PR #11: https://github.com/lensabillion/reversa-madrid-open/pull/11. PDF/TXT/MD extraction and nullable-original comparison are implemented with separate schemas, services and routers. Full make check passed: 106 backend tests, 100% branch coverage; all nine CI checks passed. docs/implementation-status.md preserves architecture assessment, evidence, gaps and handoff. Remains open until merge.
