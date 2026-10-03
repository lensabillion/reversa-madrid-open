---
type: is
id: is-01m40fgfbf2anx19zzzv3y9bqy
title: "Part 4 · Verify links: judge each candidate with signals, publish only above the precision threshold, keep evidence spans"
kind: feature
status: in_progress
priority: 0
version: 7
delegate: claude-code@dani
labels: []
dependencies:
  - type: blocks
    target: is-01m3yp5tjt1gsz6s29w5wgs9ep
  - type: blocks
    target: is-01m40fgfhe8qaj6srfqh1r6ada
  - type: blocks
    target: is-01m40fggnpz42jjw1r8667w8z3
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T08:53:51.086Z
updated_at: 2026-10-03T11:53:27.443Z
started_at: 2026-10-03T11:53:18.345Z
---
Atlas part 4. Builds on the comparison service on main (lexical-delta-v1, PR #10/#19) rather than a second matcher. For each part-3 candidate: compare the amendment's change with the passage, compute signals (rare shared phrases weighted by rarity across all 2019+ amendments, alignment, same edit same direction, legal polarity R6, meaning similarity of the changes, optional judge per D1), combine, and store score, signals, evidence spans with offsets, and status published/unconfirmed. Require the submission date to precede the amendment date. Threshold from R8 (rev-zzur). Accepted on practice-loop evidence only.

## Notes

2026-10-03 13:25 CEST, state of main at bdb0c61 (recorded by cloud session claude/eloquent-allen-jbxbmy): Unclaimed; no part-4 code on main. Inputs now available: the LinkAssessment contract with publication rules (published needs an ask dated before the amendment, spans on both sides and a tier; PR #25), fixtures including opposite request, short shall/may edit and missing date, BM25 candidates (PR #27), and the existing lexical comparison (services/comparison.py, lexical-delta-v1). Ask extraction (Agent 2) not started either. No published link exists, so plan gate 3's 13:30 checkpoint (>=20 published AI Act links) will be missed. Critical path for real links (25 points).

2026-10-03 Agent 2: PR #32 (carries the content of #30, which merged into the old bridge branch instead of main) adds services/assessment.py: a rules baseline giving published / unconfirmed / contradicted / insufficient_evidence with signals, chronology and exact quotations. Matches 6/6 fixture statuses and 5/6 tiers (a-am1-makers is reworded, fixture says copied: overlap 0.64 under the placeholder 0.7). Thresholds are placeholders; no accuracy measured. Fitted combiner and threshold calibration (rev-zzur) in progress.
