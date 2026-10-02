---
type: is
id: is-01m3yyx3pta060m8vz7nnhy7bp
title: "R12: Bring research execution under the documented quality and dependency policies"
kind: task
status: open
priority: 2
version: 4
delegate: null
labels: []
dependencies: []
parent_id: is-01m3yycrvm5f1setsgemhpa8pm
hold: null
hold_until: null
created_at: 2026-10-02T18:44:24.921Z
updated_at: 2026-10-02T18:51:10.742Z
started_at: 2026-10-02T18:51:02.458Z
---
Medium. Makefile:30-41 lints scripts and schema-validates catalogs but omits seven committed Python evidence scripts; Ruff reports 148 diagnostics there, including bare except and undefined names induced by exec-based sharing. docs/research/reversa-2026-10/evidence/README.md:20 tells users to run unpinned --with dependencies. check-docs pins softschema directly but its transient dependency tree is neither lockfile-backed nor in the backend audit, and --no-project bypasses backend no-build configuration. Put research dependencies in a locked environment, cover executable evidence with explicit gates, and either fix or clearly quarantine historical snapshots. Catalog schema success currently does not check source-path existence or factual claims. The pending Next exception approval record also needs reconciliation; PR5 was merged by the owner but has no formal review and still says pending, so do not infer lack of human authorization.

## Notes

Sol verified there are seven committed Python research evidence scripts, not eight; count corrected. Root reran the narrow Ruff check and saved all 148 diagnostics as outputs/review-2026-10-02/research-ruff.log. Main make check remains green because this scope is omitted.
