---
type: is
id: is-01m40y03anyzpc4k49ppch4h9g
title: Focus Atlas evidence on cited context so long documents remain comparable
kind: bug
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m40nw6ndb84q46r7gq1kyknj
created_at: 2026-10-03T13:07:03.125Z
updated_at: 2026-10-03T13:07:03.125Z
---
Architecture part 8 (Publish), using part 4 source spans and the shared Atlas evidence adapter; no scoring or source-text changes.

Reproduced in the real AI Act run20261003T123800Z at http://localhost:3014/atlas?law=2021-0106-COD on3October2026: select the Novartis 'echoed in' graph connection, then Read source texts side by side. At1440x1000 the first highlighted source span is at document y46768.5px. The four-column evidence grid begins y1721.5px and is60605px tall because it renders the entire44,114-character submission. At the highlighted passage, the original/amendment/final columns are blank; the legal outcome is below y62354.5px. The selected evidence cannot actually be compared side by side.

Relevant code: frontend/lib/atlas.ts excerpt() currently passes the complete source text; frontend/components/atlas-evidence.tsx Excerpt renders it; frontend/components/atlas-workspace.tsx transfers graph selection. Preserve source code-point offsets, complete cited spans, source context and correct URLs. Show bounded context windows around all cited spans (including distant spans without silently dropping any), with an explicit way to expand the original full source. Do not truncate or change the stored record or turn source excerpts into scoring inputs.

Acceptance: selecting either a short fixture link or the real long Novartis link immediately exposes the relevant highlighted text beside its amendment. Every original quotation still matches exact source offsets; supplementary context can be expanded. Verify narrow/wide layouts and multi-span cases. Regression test must use a long source with a late highlight, not only short fixture text.

Browser proof: /tmp/atlas-live-highlight-viewport.png (late quote with three blank parallel columns); /tmp/atlas-live-link-1.png (full Novartis page); /tmp/atlas-browser-verification.md. These are local session artifacts; all measured reproduction details above are retained in this bead. The old rules-2 snapshot is reproduction material, not a claim of current approved publication or influence accuracy.
