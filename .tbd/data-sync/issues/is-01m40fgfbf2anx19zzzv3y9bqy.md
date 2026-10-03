---
type: is
id: is-01m40fgfbf2anx19zzzv3y9bqy
title: "Part 4 · Verify links: judge each candidate with signals, publish only above the precision threshold, keep evidence spans"
kind: feature
status: in_progress
priority: 0
version: 13
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
child_order_hints:
  - is-01m413zp4bzsdkvj8j9sgca4yd
  - is-01m413zpaet808wjyfvghh71wx
  - is-01m414pk5tt1zztmv6tzq04bbe
hold: null
hold_until: null
created_at: 2026-10-03T08:53:51.086Z
updated_at: 2026-10-03T15:27:53.498Z
started_at: 2026-10-03T11:53:18.345Z
---
Atlas part 4. Builds on the comparison service on main (lexical-delta-v1, PR #10/#19) rather than a second matcher. For each part-3 candidate: compare the amendment's change with the passage, compute signals (rare shared phrases weighted by rarity across all 2019+ amendments, alignment, same edit same direction, legal polarity R6, meaning similarity of the changes, optional judge per D1), combine, and store score, signals, evidence spans with offsets, and status published/unconfirmed. Require the submission date to precede the amendment date. Threshold from R8 (rev-zzur). Accepted on practice-loop evidence only.

## Notes

Review-sweep fixes in PR https://github.com/lensabillion/reversa-madrid-open/pull/72 (17:30, 3 Oct).
