---
type: is
id: is-01m40fgfqa8b905kamgqhmmsjd
title: "Part 8 · Any-law command and explorer: a law's name or procedure number in, who shaped it with side-by-side evidence out, timed"
kind: feature
status: in_progress
priority: 0
version: 14
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
  - is-01m40wr0b40dx456hw7jnb0s84
  - is-01m40wvemgkxta39j8wv3znxyw
hold: null
hold_until: null
created_at: 2026-10-03T08:53:51.465Z
updated_at: 2026-10-03T13:23:56.913Z
started_at: 2026-10-03T12:25:18.808Z
---
Atlas part 8; the live 'any law' check (20 points) and the 'real links' check (25). Command: influence atlas <procedure|name> runs parts 1-6 for one law (from cache when precomputed) and the explorer shows actors, links and the three-column evidence (ask | amendment | final article). Name lookup over procedure titles and common names. Honest empty states per layer (no consultation, no amendments, not yet adopted, non-English paper not analysed). Time it from cache and from download on the demo laptop.

## Notes

2026-10-03 16:05 CEST (claude-code@omni): gate 6 split over three agents. (a) rev-k9rm: branch feat/atlas-coordinated-view, influence atlas also writes coordinated.json, GET /api/v1/atlas/{slug}/coordinated, AtlasView.modes from plan §6. (b) rev-ifao: branch feat/atlas-explorer-badges, layer badges, mode labels, coordinated-amendments panel. (c) branch fix/any-law-rehearsal: laws not used in development, cached and uncached timings with hardware into docs/implementation-status.md.
