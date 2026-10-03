---
type: is
id: is-01m414pkdehby09pckb46e2n2y
title: Part 1 · PDF extraction emits NUL for fi/fl ligatures (144 AI Act passages in 5 documents)
kind: bug
status: open
priority: 2
version: 2
labels: []
dependencies: []
parent_id: is-01m3yxjrzde6r6gw3jfr2e85bz
created_at: 2026-10-03T15:04:11.949Z
updated_at: 2026-10-03T15:08:55.753Z
---
Found while fixing rev-jesy. In the AI Act collection (2021/0106(COD), run 20261003T144014Z) 540 NUL characters appear in 144 of 29,061 passages across 5 of 790 document texts, where a PDF ligature was extracted as U+0000: for example 'signi\x00cant changes' and 'substantial modi\x00cations' in passages of doc:hys_attachment:090166e5dfcec997. Every part that matches words (BM25, prose matching, masking, outcomes) then misses those words. Fix in the PDF text extraction (map ligature glyphs to their letters, or record the unmapped glyph as an extraction warning), with a fixture PDF that uses an fi ligature.
