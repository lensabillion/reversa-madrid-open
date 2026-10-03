---
type: is
id: is-01m413zp4bzsdkvj8j9sgca4yd
title: Part 4 · Read each quoted-instruction ask's direction so the same-direction and opposite-direction checks fire
kind: bug
status: in_progress
priority: 1
version: 2
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfbf2anx19zzzv3y9bqy
hold: null
hold_until: null
created_at: 2026-10-03T14:51:41.066Z
updated_at: 2026-10-03T14:51:52.953Z
started_at: 2026-10-03T14:51:52.953Z
---
Part 4 (verify links). assess_link compares ask.direction with the amendment's direction (same_direction tier, opposite-direction contradiction), but asks_from_passages never sets a direction, so both checks are silently off on every live link. Fix: read the requested change's direction with the same cue rule as the amendment's (amendment_direction), as practice/calibrate.py measured its direction features. Prose statements state no change, so their direction stays unknown and the link says so instead of silently skipping the checks. Accepted on LobbyPlag evidence: at the copied tier the rule contradicts 0 of 136 pairs; over all 272 pairs it marks 2 positives and 5 weak negatives opposed.
