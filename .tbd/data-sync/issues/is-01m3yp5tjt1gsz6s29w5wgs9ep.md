---
type: is
id: is-01m3yp5tjt1gsz6s29w5wgs9ep
title: "Part 5 · Trace outcomes: heard, adopted by Parliament, won, by text survival into Parliament's position and the final act"
kind: feature
status: open
priority: 0
version: 5
labels: []
dependencies:
  - type: blocks
    target: is-01m40fgfhe8qaj6srfqh1r6ada
  - type: blocks
    target: is-01m3yyx3aamcphb4v8hp350npw
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-02T16:11:53.305Z
updated_at: 2026-10-03T08:54:03.696Z
---
Fill the 'passed Parliament' gap without vote records: reuse the change matcher to test whether each requested change survives from the Commission proposal into Parliament's first-reading/negotiating position and then into the final act. Gives the heard -> kept -> won funnel for the demo and a strong feature for adoption prediction. Validate on GDPR (LobbyPlag verified pairs; Amazon's Art. 26(1) phrase is absent from the final law). Pending architecture agreement (rev-0pmq) and dataset research (rev-rpoi).

## Notes

2026-10-03, Atlas re-plan (rev-sz6q): now core: the brief scores 'who actually gets their way', so 'won' needs the final article. Owner rule of 2026-10-03 (from rev-e5xh): adopted = the requested wording survives in the final law, labelled automatically. Inputs: part 1's EP position and final act, part 4's links. Output: heard / adopted by Parliament / won per ask and amendment, with the final article text as evidence.
