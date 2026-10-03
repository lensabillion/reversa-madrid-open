---
type: is
id: is-01m4126z326kmt6gdwpp96mxfz
title: "Part 3 · Exact BM25 speedup: vectorize PassageIndex.search with identical candidates"
kind: task
status: in_progress
priority: 0
version: 4
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T14:20:42.466Z
updated_at: 2026-10-03T14:26:36.444Z
started_at: 2026-10-03T14:20:47.415Z
---
find_candidates spends 212 s of the 310 s AI Act atlas run in PassageIndex.search (measured 2026-10-03: 5,660 amendments x 29,056 passages, 751M postings walked one at a time in Python; 51 words in >10% of passages cause 89% of the work). Make search exact-equivalent and fast: precompute each posting's BM25 weight at build time (it does not depend on the query) and add them with numpy, then pick the top k with the same tie-break. Acceptance: identical candidates, ranks, scores and matched terms on the AI Act (all 28,229) and on property-based random corpora against the old code as oracle; timed before/after on this laptop. Dropping common words is NOT part of this: it changed the top 5 for 258/400 sampled amendments and lost 7/188 copied-tier pairs, so it would need practice-loop evidence. Unblocks rev-bxv4 (union shortlist), which planned this speedup first.

## Notes

2026-10-03: PR #64 (https://github.com/lensabillion/reversa-madrid-open/pull/64), branch refactor/vectorized-bm25, commit 252f450. Verified: make check-backend green (1086 tests, 100% branch coverage); Hypothesis differential test vs the old walk (fails under a tie-break mutation); AI Act all 5,660 shortlists byte-identical old vs new (sha256 ba282538a949676a..., 28,229 candidates); search 219.5 s -> 3.0 s on Apple M5. Open: end-to-end make atlas timing, CI result, owner review, then record in docs/implementation-status.md and close.
