---
type: is
id: is-01m40vrxajvebhebh2bybshm00
title: Preserve complete ask inventory and eligible origins in Atlas pipeline
kind: bug
status: in_progress
priority: 1
version: 3
delegate: claude-code@vm
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
hold: null
hold_until: null
created_at: 2026-10-03T12:28:10.450Z
updated_at: 2026-10-03T14:26:21.967Z
started_at: 2026-10-03T14:16:26.533Z
---
Review of main 00033b1: build_view calls _rankings with filtered shown_asks, omitting unmatched/insufficient asks and dropping aggregation coverage gaps. trace skips unmatched asks even though outcome service supports direct final/status-quo paths. origin_links selects strongest unconfirmed before checking ask_first, allowing a late highscore to suppress a valid lower one. Passage-v0 extraction never sets keep direction. Fix denominator/coverage and chronology with end-to-end synthetic regressions; retain explicit passage-v0 limitations.

## Notes

Fixed in 524f9cf, merged to claude/great-johnson-36vizc (b468745), PR https://github.com/lensabillion/reversa-madrid-open/pull/62. Points 1 (rankings count every ask, unknown when untraced, coverage gaps kept) and 3 (eligibility before strength in origin_links) fixed. Point 2 not enabled: direct tracing measured ~130 ms/ask synthetic (4-core Xeon) => ~1 h for 29k asks; untraced asks counted unknown. Point 4 stated as limitation. make check-backend: 1144 passed, 100% coverage. Follow-ups: atlas.json size growth unmeasured; Outcomes tab renders every ranking row (~hundreds of actors) unpaged.
