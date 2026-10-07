---
type: is
id: is-01m48yd5cv7ejd873s5fyy8wge
title: Make the lineage view ETag weak (or vary it by content-coding) once gzip (#95) and cache headers (#96) are both on main
kind: task
status: closed
priority: 2
version: 4
delegate: unknown@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-06T15:48:06.683Z
updated_at: 2026-10-07T12:00:40.038Z
started_at: 2026-10-07T10:10:22.934Z
closed_at: 2026-10-07T12:00:40.038Z
close_reason: "PR #98 merged by the owner 2026-10-07: the lineage view ETag is weak (W/), shared by the gzip and plain answers; ten checks green."
resolution: null
duplicate_of: null
---
Part 8 · Publish (the view API). PR #96 sends a strong ETag computed from the view file's size and mtime; PR #95 gzips bodies of 1 KB or more. RFC 9110 says a strong validator must change whenever the representation changes, and the gzip and identity bodies are different representations with the same tag. Either mark the ETag weak (W/"..."), which keeps 304 revalidation working, or append the content-coding to the tag. Add a test that the gzip and plain answers either share a weak tag or carry different strong tags. Small; do it right after both PRs merge.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/98 opened 2026-10-07: etag() returns W/"..."; format test and the W/W case updated; new test proves gzip and plain answers share the weak tag and a gzip client revalidates to 304. Backend suite 1400 passed, 100% coverage; mutation check: 2 tests fail with a strong tag.
