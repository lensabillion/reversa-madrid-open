---
type: is
id: is-01m413zpaet808wjyfvghh71wx
title: Part 4 · Mask proposal quotations out of prose matches on the live atlas path
kind: bug
status: in_progress
priority: 1
version: 3
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m40fgfbf2anx19zzzv3y9bqy
hold: null
hold_until: null
created_at: 2026-10-03T14:51:41.262Z
updated_at: 2026-10-03T15:13:33.155Z
started_at: 2026-10-03T14:51:53.132Z
---
Part 4 (verify links). docs/plan.md section 3 says to mask text quoted from the proposal, and services/masking.py does it, but only services/calculation.py (not on the live path) calls it, so the live prose matcher can match a submission that merely quotes the proposal against an amendment inserting that same proposal wording. Fix: index the proposal's provisions once per law (mask_quoted_law rebuilt its index per call, about 10 ms a passage on the AI Act), mask 8+ word proposal quotations out of prose statements before shared phrases are found, keep evidence offsets on the original text, and say so on the link when no proposal text is available.

## Notes

PR #71 https://github.com/lensabillion/reversa-madrid-open/pull/71 (branch fix/ask-direction-and-quoted-law). make check passed (1249 backend tests, 100% branch coverage; 117 frontend tests; build; audits); 1253 backend tests after merging main cb949e9. AI Act, same run 20261003T144014Z and same 28,229 candidates: published 0 -> 0; unconfirmed copied 188 -> 42, reworded 671 -> 252; contradicted 82 -> 36; view 941 -> 330 links. Direction changes no AI Act verdict (29,055 of 29,061 asks are prose; the 6 instructions hold no obligation cue); LobbyPlag: 0 opposed pairs at the copied tier, 2 positives and 5 weak negatives opposed overall. Follow-ups rev-0vi1, rev-yfc0, rev-obw8. Awaiting CI and review.
