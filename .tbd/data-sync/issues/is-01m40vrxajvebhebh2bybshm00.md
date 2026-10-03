---
type: is
id: is-01m40vrxajvebhebh2bybshm00
title: Preserve complete ask inventory and eligible origins in Atlas pipeline
kind: bug
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
created_at: 2026-10-03T12:28:10.450Z
updated_at: 2026-10-03T12:28:10.450Z
---
Review of main 00033b1: build_view calls _rankings with filtered shown_asks, omitting unmatched/insufficient asks and dropping aggregation coverage gaps. trace skips unmatched asks even though outcome service supports direct final/status-quo paths. origin_links selects strongest unconfirmed before checking ask_first, allowing a late highscore to suppress a valid lower one. Passage-v0 extraction never sets keep direction. Fix denominator/coverage and chronology with end-to-end synthetic regressions; retain explicit passage-v0 limitations.
