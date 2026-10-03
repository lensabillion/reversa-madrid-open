---
type: is
id: is-01m40fgfbf2anx19zzzv3y9bqy
title: "Part 4 · Verify links: judge each candidate with signals, publish only above the precision threshold, keep evidence spans"
kind: feature
status: open
priority: 0
version: 4
labels: []
dependencies:
  - type: blocks
    target: is-01m3yp5tjt1gsz6s29w5wgs9ep
  - type: blocks
    target: is-01m40fgfhe8qaj6srfqh1r6ada
  - type: blocks
    target: is-01m40fggnpz42jjw1r8667w8z3
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-03T08:53:51.086Z
updated_at: 2026-10-03T08:54:04.227Z
---
Atlas part 4. Builds on the comparison service on main (lexical-delta-v1, PR #10/#19) rather than a second matcher. For each part-3 candidate: compare the amendment's change with the passage, compute signals (rare shared phrases weighted by rarity across all 2019+ amendments, alignment, same edit same direction, legal polarity R6, meaning similarity of the changes, optional judge per D1), combine, and store score, signals, evidence spans with offsets, and status published/unconfirmed. Require the submission date to precede the amendment date. Threshold from R8 (rev-zzur). Accepted on practice-loop evidence only.
