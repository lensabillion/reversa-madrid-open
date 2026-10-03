---
type: is
id: is-01m40fgfqa8b905kamgqhmmsjd
title: "Part 8 · Any-law command and explorer: a law's name or procedure number in, who shaped it with side-by-side evidence out, timed"
kind: feature
status: in_progress
priority: 0
version: 11
delegate: claude-code@vm
labels: []
dependencies:
  - type: blocks
    target: is-01m40fgfxhtzscc80t35zx2kg6
parent_id: is-01m3ygrva6wcq297g7j12g99c2
child_order_hints:
  - is-01m40vrt8yjkzzm7bkdc9qx49w
  - is-01m40vrxajvebhebh2bybshm00
  - is-01m40w1dw2b2b7w88a67t494ve
  - is-01m40nw41zbvnpsq0zexzfhx42
  - is-01m40nw6ndb84q46r7gq1kyknj
  - is-01m40vj7j8teddwx12kvr1x7yk
hold: null
hold_until: null
created_at: 2026-10-03T08:53:51.465Z
updated_at: 2026-10-03T12:34:04.129Z
started_at: 2026-10-03T12:25:18.808Z
---
Atlas part 8; the live 'any law' check (20 points) and the 'real links' check (25). Command: influence atlas <procedure|name> runs parts 1-6 for one law (from cache when precomputed) and the explorer shows actors, links and the three-column evidence (ask | amendment | final article). Name lookup over procedure titles and common names. Honest empty states per layer (no consultation, no amendments, not yet adopted, non-English paper not analysed). Time it from cache and from download on the demo laptop.

## Notes

2026-10-03 13:25 CEST, state of main at bdb0c61 (recorded by cloud session claude/eloquent-allen-jbxbmy): PR #24 (feat/atlas-explorer: explorer, graph and evidence components on fixtures; CI green) and PR #28 (graph projection and outcome rankings services; CI green) are open. CLI/API not started. Child beads rev-k9rm (CLI/API, Agent 1) and rev-ifao (UI, Agent 3) are named in docs/agents/agent-1-handoff.md but not present in the shared tracker.

2026-10-03 14:15 CEST: PR #45 merged (127d3f5). CLI/API half done (rev-k9rm closed): make atlas LAW=... writes data/laws/<procedure>/atlas.json; GET /api/v1/atlas/{slug} serves it. Graph break fixed (amendments cite their Parltrack dump). Open on this bead: the /atlas page that reads the API (rev-ifao), the alias table for common names ('AI Act'), and timing on the demo laptop from download and from cache.

2026-10-03 14:35 CEST: PR #46 (https://github.com/lensabillion/reversa-madrid-open/pull/46, branch claude/eloquent-allen-jbxbmy, head 4405cba): /atlas page reading GET /api/v1/atlas(/{slug}); browser-checked against the real backend on the offline test world; also builds the view's scoring limitation from assessment constants (rules-2). CI 9/9 green. rev-ifao (Agent 3) should review. Parallel: rev-w6u0 (aliases), rev-bxv4 (candidate union), rev-6c1o (setup).

2026-10-03 14:28 CEST: PR #46 merged by the owner (CI 9/9 green on 4405cba). The /atlas page is on main. Still open here: real-law run and timing on the demo laptop; common names (rev-w6u0, in progress).
