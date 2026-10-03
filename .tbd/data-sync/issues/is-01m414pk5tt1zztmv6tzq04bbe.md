---
type: is
id: is-01m414pk5tt1zztmv6tzq04bbe
title: Part 3 · Read the direction a prose ask requests, measured on labelled prose before part 4 uses it
kind: task
status: open
priority: 2
version: 2
labels: []
dependencies: []
parent_id: is-01m40fgfbf2anx19zzzv3y9bqy
created_at: 2026-10-03T15:04:11.706Z
updated_at: 2026-10-03T15:08:55.290Z
---
Found while fixing rev-jesy. Ask direction is now read from quoted instructions only, by the calibrated cue rule (assessment.requested_direction). On the AI Act (2021/0106(COD), collect run 20261003T144014Z) that gives 0 known directions: 29,055 of 29,061 asks are prose, and none of the 6 quoted instructions holds an obligation cue. So part 4's same-direction tier and opposite-direction contradiction still never run on real prose. A cue count over a whole argued passage is wrong ('should not be required' reads stricter), so a prose reader (cue rules near the shared phrase, direction.py's phrase-aware cues, or the meaning judge under D1) must first be measured on a labelled prose sample, reporting agreement and the effect on contradicted/unconfirmed counts, before Ask.direction is set from prose.
