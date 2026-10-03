---
type: is
id: is-01m40vj7j8teddwx12kvr1x7yk
title: Part 1 · Resolve common law names (alias table) and read JSON Lines safely (split on \n only)
kind: feature
status: closed
priority: 0
version: 4
delegate: claude-code@vm
labels: []
dependencies: []
parent_id: is-01m40fgfqa8b905kamgqhmmsjd
hold: null
hold_until: null
created_at: 2026-10-03T12:24:31.560Z
updated_at: 2026-10-03T13:23:20.253Z
started_at: 2026-10-03T13:15:30.419Z
closed_at: 2026-10-03T13:23:20.252Z
close_reason: "PR #53 merged 2026-10-03 (https://github.com/lensabillion/reversa-madrid-open/pull/53): LAW_ALIASES extends PR #49's table to 28 procedures / 84 names (EN/DE/FR/ES), name_key normalisation, ambiguity choices, missing aliased procedure stops, resolved-law line before stages; CI 9/9 green; 1011 backend tests at 100% on main+#52 merged. The JSON Lines reader half landed in #47. Not yet checked: the 77 added names against a real dossiers dump (command in the PR)."
resolution: null
duplicate_of: null
---
Port from unmerged PR #36 (feat/collect-command): common-name aliases in services/collect.resolve_law ('AI Act' -> 2021/0106(COD)), checked mappings only; extraction/records.py reader splits on \n only so U+2028/U+0085 inside JSON strings survive. Serves the live any-law check (jury names a law by common name). Branch feat/law-aliases (subagent, 2026-10-03).

## Notes

2026-10-03 15:10 CEST: PR #53 (https://github.com/lensabillion/reversa-madrid-open/pull/53, branch feat/law-aliases) extends PR #49's alias table: 28 procedures / 84 names in EN/DE/FR/ES, name_key normalisation, ambiguity choices, missing aliased procedure stops, resolved-law line before stages. 1003 backend tests, 100% coverage. #49's 7 names checked against the real catalog; the 77 added against public pages only. The JSON Lines reader part landed in #47.
