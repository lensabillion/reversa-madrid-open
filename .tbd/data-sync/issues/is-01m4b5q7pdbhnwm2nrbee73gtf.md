---
type: is
id: is-01m4b5q7pdbhnwm2nrbee73gtf
title: Rename current project branding to influence
kind: task
status: in_progress
priority: 2
version: 3
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
hold: null
hold_until: null
created_at: 2026-10-07T12:34:25.608Z
updated_at: 2026-10-07T12:48:37.971Z
started_at: 2026-10-07T12:34:41.453Z
---
Owner decision 7 October 2026: project name is lowercase influence, not Atlas. Part8 branding and current documentation. Update visible UI/API/project titles and current descriptions, retaining exact organizer brief title as historical attribution and existing technical identifiers/artifact formats unless required for visible branding. Verify affected existing tests and record decision.

## Notes

Implemented lowercase influence across visible website branding, browser/social metadata, API documentation, CLI help, generated reports, private frontend package identity and current contributor guides. The owner decision is recorded in docs/implementation-status.md. Existing atlas command/artifact/schema identifiers and historical organizer titles remain compatible.

PR: https://github.com/lensabillion/reversa-madrid-open/pull/100
Branch: codex/influence-branding
Head: b3fbae7

Validation: final make check exited 0 (1,400 backend tests; 100% coverage of 8,864 statements and 2,284 branches; 59 frontend tests; six catalogs; strict types/lint/format; production build; configured audits clean). All ten GitHub CI checks passed, including the existing container smoke gate. No live-browser acceptance run was performed. No analytic behavior changed.

Implementation complete, PR open and unmerged. Keep bead open until merge under repository workflow. Separate analytical repairs are tracked by rev-1i73 and its follow-ups.
