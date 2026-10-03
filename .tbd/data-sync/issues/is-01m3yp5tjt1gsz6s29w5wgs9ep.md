---
type: is
id: is-01m3yp5tjt1gsz6s29w5wgs9ep
title: "Part 5 · Trace outcomes: heard, adopted by Parliament, won, by text survival into Parliament's position and the final act"
kind: feature
status: in_progress
priority: 0
version: 10
delegate: claude-code@dani
labels: []
dependencies:
  - type: blocks
    target: is-01m40fgfhe8qaj6srfqh1r6ada
  - type: blocks
    target: is-01m3yyx3aamcphb4v8hp350npw
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T16:11:53.305Z
updated_at: 2026-10-03T15:27:49.438Z
started_at: 2026-10-03T11:53:18.376Z
---
Fill the 'passed Parliament' gap without vote records: reuse the change matcher to test whether each requested change survives from the Commission proposal into Parliament's first-reading/negotiating position and then into the final act. Gives the heard -> kept -> won funnel for the demo and a strong feature for adoption prediction. Validate on GDPR (LobbyPlag verified pairs; Amazon's Art. 26(1) phrase is absent from the final law). Pending architecture agreement (rev-0pmq) and dataset research (rev-rpoi).

## Notes

Review-sweep fixes in PR https://github.com/lensabillion/reversa-madrid-open/pull/72 (17:30, 3 Oct).
