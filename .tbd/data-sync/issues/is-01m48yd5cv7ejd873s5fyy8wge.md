---
type: is
id: is-01m48yd5cv7ejd873s5fyy8wge
title: Make the lineage view ETag weak (or vary it by content-coding) once gzip (#95) and cache headers (#96) are both on main
kind: task
status: open
priority: 2
version: 1
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
created_at: 2026-10-06T15:48:06.683Z
updated_at: 2026-10-06T15:48:06.683Z
---
Part 8 · Publish (the view API). PR #96 sends a strong ETag computed from the view file's size and mtime; PR #95 gzips bodies of 1 KB or more. RFC 9110 says a strong validator must change whenever the representation changes, and the gzip and identity bodies are different representations with the same tag. Either mark the ETag weak (W/"..."), which keeps 304 revalidation working, or append the content-coding to the tag. Add a test that the gzip and plain answers either share a weak tag or carry different strong tags. Small; do it right after both PRs merge.
