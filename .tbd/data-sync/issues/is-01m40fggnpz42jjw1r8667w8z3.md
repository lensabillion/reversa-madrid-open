---
type: is
id: is-01m40fggnpz42jjw1r8667w8z3
title: "Practice loop: blind audit of a random sample of published 2019+ links, precision with a Wilson interval"
kind: task
status: in_progress
priority: 1
version: 5
delegate: claude-code@dani
labels: []
dependencies:
  - type: blocks
    target: is-01m40fggfj56f94fph17m88zna
parent_id: is-01m3ygrva6wcq297g7j12g99c2
hold: null
hold_until: null
created_at: 2026-10-03T08:53:52.438Z
updated_at: 2026-10-03T15:27:50.882Z
started_at: 2026-10-03T11:53:18.383Z
---
Measures part 4 where LobbyPlag cannot (2019+, paraphrase, other languages). Sample links uniformly from the published graph with a printed seed; each reader sees both texts without the score and marks real influence / boilerplate / unclear; store audit labels apart from model output; report precision and its 95% Wilson interval in the report. Audit labels never edit the graph (AGENTS.md data rules).

## Notes

Review-sweep fixes in PR https://github.com/lensabillion/reversa-madrid-open/pull/72 (17:30, 3 Oct).
