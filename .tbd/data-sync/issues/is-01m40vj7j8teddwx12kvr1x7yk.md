---
type: is
id: is-01m40vj7j8teddwx12kvr1x7yk
title: Part 1 · Resolve common law names (alias table) and read JSON Lines safely (split on \n only)
kind: feature
status: open
priority: 0
version: 1
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
created_at: 2026-10-03T12:24:31.560Z
updated_at: 2026-10-03T12:24:31.560Z
---
Port from unmerged PR #36 (feat/collect-command): common-name aliases in services/collect.resolve_law ('AI Act' -> 2021/0106(COD)), checked mappings only; extraction/records.py reader splits on \n only so U+2028/U+0085 inside JSON strings survive. Serves the live any-law check (jury names a law by common name). Branch feat/law-aliases (subagent, 2026-10-03).
