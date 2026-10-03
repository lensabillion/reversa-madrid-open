---
type: is
id: is-01m4160qq7hz09starm9vszwak
title: Part 8 · Evidence cards show a final outcome traced through a different amendment than the card's
kind: bug
status: open
priority: 1
version: 1
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
created_at: 2026-10-03T15:27:12.615Z
updated_at: 2026-10-03T15:27:12.615Z
---
Found 3 Oct. frontend/lib/atlas.ts keys final-act outcomes by ask (finalOutcomes.get(ask.ask_id)) and attaches that outcome to every link card of the ask. The backend traces each ask once, through its origin link's amendment, and sets Outcome.link_id to None unless the link is published, so the adapter's link/amendment consistency check cannot fire. AI Act view (run 20261003T150336Z): 426 of 941 cards under rules-3 and 95 of 330 under rules-4 show final text traced through another amendment (e.g. card for ENVI PE704.585-125 shows the outcome via ENVI PE704.585-84); 7 (rules-3) / 1 (rules-4) contradicted cards display a final-act outcome from the ask's other link. Fix: only show an outcome on the card whose amendment_id it was traced through (and say 'traced via another amendment' otherwise), and/or have the backend record the traced link id for unconfirmed origins with a separate published flag; add a contract test with an ask that has two links.
