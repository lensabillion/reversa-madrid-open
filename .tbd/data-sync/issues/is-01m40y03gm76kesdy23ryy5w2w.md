---
type: is
id: is-01m40y03gm76kesdy23ryy5w2w
title: Connect supplied Atlas ranking evidence IDs to source anchors
kind: bug
status: open
priority: 2
version: 1
labels: []
dependencies: []
parent_id: is-01m40m9petsrdhjvg47v8nx85f
created_at: 2026-10-03T13:07:03.315Z
updated_at: 2026-10-03T13:07:03.315Z
---
Architecture parts7/8 (Analyse/Publish). Preserve backend ranking order, numerators and denominators; make supplied ranking evidence reachable rather than recomputing ranks or inferring provenance in the browser.

Observed on the real AI Act run20261003T123800Z at /atlas?law=2021-0106-COD -> See the outcomes:277 actor rows render, and every Evidence cell says 'Source evidence unavailable.' Backend RankingRow supplies evidence_record_ids, but frontend/components/atlas-law-browser.tsx prepareLawAtlas maps every row with sources:[] (currently aroundline122). frontend/components/atlas-analysis.tsx therefore cannot display evidence anchors. Shared source/document/ask/article records already accompany the view.

Acceptance: resolve available supplied evidence IDs to the corresponding published link evidence or exact source record/URL; use stable deduplicated anchors and preserve the row's actor/procedure association. Distinguish an unavailable/missing record explicitly. Do not attach an unrelated convenient source or claim unconfirmed links as published support. Handle document-, article- and passage-relative IDs according to the shared adapter. Test an actual backend-shaped ranking with available evidence, missing evidence, duplicate IDs and unknown outcomes; clicking a row anchor must reach the record named by that row.

Browser evidence: /tmp/atlas-live-populated-outcomes.png and /tmp/atlas-browser-verification.md; API view holds the supplied evidence_record_ids. Local screenshots are session artifacts; the exact failure and reproduction above are recorded durably here. Related but separate issue rev-539s concerns complete ask inventory and origin selection, not evidence navigation. The historical snapshot is reproduction data, not acceptance of its influence findings.
