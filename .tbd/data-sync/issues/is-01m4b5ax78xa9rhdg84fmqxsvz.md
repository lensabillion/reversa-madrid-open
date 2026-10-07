---
type: is
id: is-01m4b5ax78xa9rhdg84fmqxsvz
title: Prevent reports from combining incompatible run snapshots
kind: bug
status: open
priority: 2
version: 1
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
created_at: 2026-10-07T12:27:41.671Z
updated_at: 2026-10-07T12:27:41.671Z
---
Part8. report.load_law reads views independently; coverage_section warns on run_id mismatch but headline sections still use old views beside latest collection metadata/spend. Reject incompatible inputs or retain coherent historical bundles with explicit per-section provenance. Test schema-valid mismatched views cannot contribute current-run combined claims.
