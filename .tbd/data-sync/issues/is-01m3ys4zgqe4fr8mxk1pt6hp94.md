---
type: is
id: is-01m3ys4zgqe4fr8mxk1pt6hp94
title: "Make the explainer readable on GitHub: Markdown with Mermaid diagrams"
kind: task
status: closed
priority: 2
version: 4
delegate: claude-code@lensas-macbook-air.local
labels: []
dependencies: []
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T17:03:51.318Z
updated_at: 2026-10-02T21:21:59.437Z
started_at: 2026-10-02T17:03:51.658Z
closed_at: 2026-10-02T21:21:59.437Z
close_reason: "PR #9 merged into main (18fffb2); explainer renders on GitHub as Markdown; 3/3 Mermaid diagrams parse."
resolution: null
duplicate_of: null
---
GitHub shows HTML files as source code. Convert docs/explainer/influence-graph-primer.html to Markdown (tables, Mermaid diagrams) as the repository's copy, remove the HTML file, and point README and AGENTS.md at it. The styled page stays at its published link.

## Notes

PR https://github.com/lensabillion/reversa-madrid-open/pull/9 (base main). 3/3 Mermaid diagrams parse (Mermaid 12.0.0); a reserved node id was caught and fixed.
