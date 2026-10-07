---
type: is
id: is-01m4b5b85x9dccc8q1aypzxjnb
title: Lock and audit documentation validator dependencies
kind: bug
status: open
priority: 2
version: 1
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
created_at: 2026-10-07T12:27:52.893Z
updated_at: 2026-10-07T12:27:52.893Z
---
Tooling/supply chain. Makefile40-42 runs uv --no-project --with softschema==0.8.1 outside locked backend config/audit and no-build enforcement. Exact direct pin and14-day cutoff exist, but transitives dynamically resolve. Use locked tools env or dependency group, no source builds, and audit actual lock. Verify locked fresh install and subsequent offline execution.
