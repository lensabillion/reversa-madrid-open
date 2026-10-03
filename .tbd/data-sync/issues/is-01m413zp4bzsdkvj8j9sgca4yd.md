---
type: is
id: is-01m413zp4bzsdkvj8j9sgca4yd
title: Part 4 · Read each quoted-instruction ask's direction so the same-direction and opposite-direction checks fire
kind: bug
status: closed
priority: 1
version: 4
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfbf2anx19zzzv3y9bqy
hold: null
hold_until: null
created_at: 2026-10-03T14:51:41.066Z
updated_at: 2026-10-03T15:29:19.834Z
started_at: 2026-10-03T14:51:52.953Z
closed_at: 2026-10-03T15:29:19.833Z
close_reason: "Merged in PR #71 (merge 4db382d). make check passed; AI Act rules-3 -> rules-4 on the same 28,229 candidates: published 0 -> 0, unconfirmed 859 -> 294, contradicted 82 -> 36, view 941 -> 330 links; LobbyPlag shows no opposed copied-tier pair. Follow-ups rev-0vi1, rev-yfc0, rev-obw8."
resolution: null
duplicate_of: null
---
Part 4 (verify links). assess_link compares ask.direction with the amendment's direction (same_direction tier, opposite-direction contradiction), but asks_from_passages never sets a direction, so both checks are silently off on every live link. Fix: read the requested change's direction with the same cue rule as the amendment's (amendment_direction), as practice/calibrate.py measured its direction features. Prose statements state no change, so their direction stays unknown and the link says so instead of silently skipping the checks. Accepted on LobbyPlag evidence: at the copied tier the rule contradicts 0 of 136 pairs; over all 272 pairs it marks 2 positives and 5 weak negatives opposed.

## Notes

PR #71 https://github.com/lensabillion/reversa-madrid-open/pull/71 (branch fix/ask-direction-and-quoted-law). make check passed (1249 backend tests, 100% branch coverage; 117 frontend tests; build; audits); 1253 backend tests after merging main cb949e9. AI Act, same run 20261003T144014Z and same 28,229 candidates: published 0 -> 0; unconfirmed copied 188 -> 42, reworded 671 -> 252; contradicted 82 -> 36; view 941 -> 330 links. Direction changes no AI Act verdict (29,055 of 29,061 asks are prose; the 6 instructions hold no obligation cue); LobbyPlag: 0 opposed pairs at the copied tier, 2 positives and 5 weak negatives opposed overall. Follow-ups rev-0vi1, rev-yfc0, rev-obw8. Awaiting CI and review.
