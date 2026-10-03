---
type: is
id: is-01m40fgfbf2anx19zzzv3y9bqy
title: "Part 4 · Verify links: judge each candidate with signals, publish only above the precision threshold, keep evidence spans"
kind: feature
status: in_progress
priority: 0
version: 12
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
updated_at: 2026-10-03T15:04:11.706Z
started_at: 2026-10-03T11:53:18.345Z
---
Atlas part 4. Builds on the comparison service on main (lexical-delta-v1, PR #10/#19) rather than a second matcher. For each part-3 candidate: compare the amendment's change with the passage, compute signals (rare shared phrases weighted by rarity across all 2019+ amendments, alignment, same edit same direction, legal polarity R6, meaning similarity of the changes, optional judge per D1), combine, and store score, signals, evidence spans with offsets, and status published/unconfirmed. Require the submission date to precede the amendment date. Threshold from R8 (rev-zzur). Accepted on practice-loop evidence only.

## Notes

2026-10-03 13:25 CEST, state of main at bdb0c61 (recorded by cloud session claude/eloquent-allen-jbxbmy): Unclaimed; no part-4 code on main. Inputs now available: the LinkAssessment contract with publication rules (published needs an ask dated before the amendment, spans on both sides and a tier; PR #25), fixtures including opposite request, short shall/may edit and missing date, BM25 candidates (PR #27), and the existing lexical comparison (services/comparison.py, lexical-delta-v1). Ask extraction (Agent 2) not started either. No published link exists, so plan gate 3's 13:30 checkpoint (>=20 published AI Act links) will be missed. Critical path for real links (25 points).

2026-10-03 Agent 2: PR #32 (carries the content of #30, which merged into the old bridge branch instead of main) adds services/assessment.py: a rules baseline giving published / unconfirmed / contradicted / insufficient_evidence with signals, chronology and exact quotations. Matches 6/6 fixture statuses and 5/6 tiers (a-am1-makers is reworded, fixture says copied: overlap 0.64 under the placeholder 0.7). Thresholds are placeholders; no accuracy measured. Fitted combiner and threshold calibration (rev-zzur) in progress.

2026-10-03 Agent 2: PR #43 changes assess_link to publish only the copied tier (thresholds 0.75 and 0.32, rules-2) per the #40 calibration; reworded is labelled but unpublished until an audit clears it. The invented fixture now publishes no link.

2026-10-03 Agent 2, first real-data run of influence atlas on the AI Act (2021/0106(COD), --no-attachments): 0 published, 31 unconfirmed, 12958 contradicted, graph of 1 node. Cause: the part 4 rules were calibrated on clean edit-vs-edit LobbyPlag pairs and do not transfer to prose. (1) The negation guard fires on 47% of top candidates (a ~63-word passage almost always holds a 'not'/'no'). (2) Symmetric Dice cannot exceed ~0.28 for ~8 changed words against a ~63-word passage, so the 0.75 copied threshold is unreachable. (3) Coverage of changed words is trivially 1.0 on common words, so it needs rarity and phrases. Next: prose-aware scoring (coverage weighted by rarity, negation near the matched words) as its own PR, then recalibrate on prose. The 352 PDF attachments were not read.
