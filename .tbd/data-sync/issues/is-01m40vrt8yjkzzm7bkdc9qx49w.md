---
type: is
id: is-01m40vrt8yjkzzm7bkdc9qx49w
title: Enforce independent audit before runtime Atlas publication
kind: bug
status: open
priority: 1
version: 4
delegate: codex@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
hold: null
hold_until: null
created_at: 2026-10-03T12:28:07.325Z
updated_at: 2026-10-03T12:43:45.158Z
started_at: 2026-10-03T12:42:58.980Z
---
Review of main 00033b1: services/pipeline.py calls assess_link with default copied publication. PR40 copied cutoff .75 has held-out35/36 pointprecision .9722 but Wilsonlower .8583, below .90; assessment.py comment incorrectly says held-out bound clears floor. Runtime has no independent audit binding, unlike development calculate_links. Correct evidence wording, bind accepted frozen policy, and keep unaudited links explicitly unconfirmed. Add regression through build_view.

## Notes

Scope clarification from docs/plan.md acceptance order: Gate 3 asks for practice-backed thresholds and 20 links/10 readings; the independent 40-link/two-reader audit is Gate 7. Do not treat absence of that later audit alone as a Gate 3 failure or disable provisional copied links without considering this sequence. Verified defect remains the comment claiming held-out Wilson floor clearance (.8583 does not clear .90); final publication assurance needs Gate 7 evidence. The stricter development calculator gate is not currently wired to main.
