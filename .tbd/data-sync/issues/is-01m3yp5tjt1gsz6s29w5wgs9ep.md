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
child_order_hints:
  - is-01m4160qgsmg7j4nkgvr31j0wg
hold: null
hold_until: null
created_at: 2026-10-02T16:11:53.305Z
updated_at: 2026-10-03T15:27:12.408Z
started_at: 2026-10-03T11:53:18.376Z
---
Fill the 'passed Parliament' gap without vote records: reuse the change matcher to test whether each requested change survives from the Commission proposal into Parliament's first-reading/negotiating position and then into the final act. Gives the heard -> kept -> won funnel for the demo and a strong feature for adoption prediction. Validate on GDPR (LobbyPlag verified pairs; Amazon's Art. 26(1) phrase is absent from the final law). Pending architecture agreement (rev-0pmq) and dataset research (rev-rpoi).

## Notes

2026-10-03, Atlas re-plan (rev-sz6q): now core: the brief scores 'who actually gets their way', so 'won' needs the final article. Owner rule of 2026-10-03 (from rev-e5xh): adopted = the requested wording survives in the final law, labelled automatically. Inputs: part 1's EP position and final act, part 4's links. Output: heard / adopted by Parliament / won per ask and amendment, with the final article text as evidence.

2026-10-03 13:25 CEST, state of main at bdb0c61 (recorded by cloud session claude/eloquent-allen-jbxbmy): Unclaimed; no part-5 code on main. Inputs available: repositories/cellar.py splits proposals and final acts into ArticleVersion records (AI Act final 113 articles / 500 paragraphs, proposal 85 articles; reported) and the Outcome contract (PR #25). Gap: Parliament's position text is not obtained (CELLAR links only the resolution 52024AP0138; EP API adopted-texts untested). The assignment requires outcomes for every ask, not only linked ones.

2026-10-03 Agent 2: PR #31 adds services/outcomes.py (trace_outcomes): provisions aligned by text not number; full / partial / not_observed / unknown; missing text and no aligned provision are unknown; contradicted or undated asks are traced directly, not through the amendment. Differs from two fixture examples on purpose (a-acme unknown; a-city kind wording). Fixture only; status-quo wins and reworded survival not implemented.

2026-10-03 Agent 2: PRs #31 (trace_outcomes) merged. PR #38 adds status-quo wins (direction keep: full, kind status_quo when the provision survives word for word; never traced through an amendment). Reworded survival still not implemented.
