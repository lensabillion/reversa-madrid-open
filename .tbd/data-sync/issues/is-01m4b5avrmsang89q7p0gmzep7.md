---
type: is
id: is-01m4b5avrmsang89q7p0gmzep7
title: Invalidate batch resumes when inputs options or derived dependencies change
kind: bug
status: open
priority: 2
version: 1
labels: []
dependencies: []
parent_id: is-01m4b4wbqac2z2hvn352znp92z
created_at: 2026-10-07T12:27:40.179Z
updated_at: 2026-10-07T12:27:40.179Z
---
Parts1,3-7. batch.py257-278 reuses any manifest and skips solely by run_id. --attachments after default no-attachments silently reuses old bundle; changed sources/code and atlas dependent directions can remain stale. Reuse collect's fingerprint checks and fingerprint derivative dependencies/revisions/options. Test changed attachments, source, method, atlas dependency, malformed same-run output and unchanged reuse.
