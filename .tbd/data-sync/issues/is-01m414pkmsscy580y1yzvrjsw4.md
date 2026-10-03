---
type: is
id: is-01m414pkmsscy580y1yzvrjsw4
title: Part 3 · Measure masking proposal quotations before BM25, so quoting passages do not take candidate slots
kind: task
status: open
priority: 2
version: 1
labels: []
dependencies: []
parent_id: is-01m3z9e7eesds3s8v38tswk2p6
created_at: 2026-10-03T15:04:12.184Z
updated_at: 2026-10-03T15:04:12.184Z
---
Found while fixing rev-805l. Part 4 now masks 8+ word proposal quotations out of prose (services/masking.py QuotedLaw), but part 3's BM25 still indexes the unmasked passage. On the AI Act 2,249 of 29,061 asks quote the proposal at length; such a passage can rank in an amendment's top 5 by sharing the proposal's words, and then part 4 finds nothing. Masking before indexing could free those slots, but it changes candidates, so it needs recall evidence: report Recall@k on LobbyPlag and the candidate overlap and link counts on the AI Act, before and after.
