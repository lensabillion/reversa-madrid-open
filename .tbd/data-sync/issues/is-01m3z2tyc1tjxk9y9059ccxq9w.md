---
type: is
id: is-01m3z2tyc1tjxk9y9059ccxq9w
title: Extract PDF and text uploads into a validated page-aware document contract
kind: feature
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T19:53:08.224Z
updated_at: 2026-10-02T19:53:08.224Z
---
Shared ingestion service and thin HTTP adapter for public PDF/text inputs. Preserve page numbers and extracted text, bound input bytes/pages/output, reject corrupt/encrypted/unsupported files explicitly, identify scanned pages without inventing OCR, support frontend extraction review and future batch reuse. Pin pypdf under supply-chain policy, tests/full gates/first-principles PR. Separate from semantic scoring/adoption.
