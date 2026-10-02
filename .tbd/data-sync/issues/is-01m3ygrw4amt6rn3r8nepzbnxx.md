---
type: is
id: is-01m3ygrw4amt6rn3r8nepzbnxx
title: Propose the architecture and tool choices, and agree them with the user
kind: task
status: in_progress
priority: 1
version: 5
delegate: codex@lensas-macbook-air.local
labels: []
dependencies:
  - type: blocks
    target: is-01m3ygrwb65kmfggfxnx6dtsys
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-02T14:37:26.025Z
updated_at: 2026-10-02T18:26:28.416Z
started_at: 2026-10-02T18:26:08.218Z
---
No build code until the user agrees the architecture and tools.

## Notes

2026-10-02 repository orientation: fetched origin and pulled main with --ff-only; already up to date at 18fffb2. Read organizer brief, explainer, API and frontend entry points. Current code is FastAPI /health plus Next.js landing page, not the scoring pipeline. Recommended sequence: input contracts and baseline-law loading; delta extraction and passage retrieval; deterministic scoring baseline and organization-grouped evaluation; optional evaluated language-model judge; separate adoption model with temporal cutoff; evidence-backed graph and tracer; timed end-to-end CSV rehearsal. Suggested model routing: Astra for difficult legal reasoning and evaluation diagnosis, Sol for routine engineering, Luna for bounded repetitive extraction; user mechanical-model sentence unfinished. Architecture and runtime judge choice remain proposals, not approved decisions. No source edits or new test runs in this orientation.
