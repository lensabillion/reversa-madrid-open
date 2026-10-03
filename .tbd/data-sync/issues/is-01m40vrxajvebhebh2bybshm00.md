---
type: is
id: is-01m40vrxajvebhebh2bybshm00
title: Preserve complete ask inventory and eligible origins in Atlas pipeline
kind: bug
status: in_progress
priority: 1
version: 4
delegate: claude-code@vm
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
hold: null
hold_until: null
created_at: 2026-10-03T12:28:10.450Z
updated_at: 2026-10-03T14:31:52.041Z
started_at: 2026-10-03T14:16:26.533Z
---
Review of main 00033b1: build_view calls _rankings with filtered shown_asks, omitting unmatched/insufficient asks and dropping aggregation coverage gaps. trace skips unmatched asks even though outcome service supports direct final/status-quo paths. origin_links selects strongest unconfirmed before checking ask_first, allowing a late highscore to suppress a valid lower one. Passage-v0 extraction never sets keep direction. Fix denominator/coverage and chronology with end-to-end synthetic regressions; retain explicit passage-v0 limitations.

## Notes

Now in PR https://github.com/lensabillion/reversa-madrid-open/pull/67 (PR #62 merged before this fix landed; branch rebuilt on main 94e6f50, head c330458).
